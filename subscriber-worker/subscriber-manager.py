import pickle
import platform
import io
import os
import sys
import pika
import redis
import hashlib
import json
import requests
import time
import datetime
import smtplib
import logging
import queue
import threading
import time


hostname = platform.node()
items_queue = queue.Queue()
timeInterval = 120
running = True
##Rabbit MQ commands 
## CMD SUBCMD ARG1 ARG2 ARG3
## CMD - 00 Default 01 subscribe, 02 - unsubscribe, 03 0nWeatherChange
## SUBCMD - 00 Default
## (ARG1 ARG2 ARG3) - (null null null) Default
## 
redisHost = os.getenv("REDIS_HOST") or "localhost"
rabbitMQHost = os.getenv("RABBITMQ_HOST") or "localhost"
adminEmailId = ''
adminEmailPsw = '='
#directionsdb = redis.Redis(host='redis', charset="utf-8", db=1, decode_responses=True)
#weatherdb = redis.Redis(host='redis', charset="utf-8", db=0, decode_responses=True)
subscriptionListDB = redis.Redis(host=redisHost, charset="utf-8", db=2, decode_responses=True)
print(f"Connecting to rabbitmq({rabbitMQHost}) and redis({redisHost})")

def sendGmail(receiiverEmailId, senderEmailId, senderEmailPsw, content):
   print("sending mail to "+receiiverEmailId)
   s = smtplib.SMTP('smtp.gmail.com', 587)
   s.starttls()
   s.login(senderEmailId, senderEmailPsw)
   s.sendmail(senderEmailId, receiiverEmailId, content)
   s.quit()

subscriberList = []
def timerThread():
   while running: 
    print("sleeping timer thread")
    sys.stdout.flush() 
    time.sleep(timeInterval)
    print("sending request from timer thread")
    sys.stdout.flush()
    items_queue.put("floodEmail")

def items_queue_worker():
    subscriberListLocal = []
    print("Thread started")
    sys.stdout.flush()
    while running:
        try:
            item = items_queue.get(timeout=1)
            print("receiving an item in queue "+ item)
            sys.stdout.flush()
            
            if item is None:
                continue
            print(subscriberListLocal)
            sys.stdout.flush()
            if(item == "floodEmail"):
              subscriberListLocal = process_item("",subscriberListLocal)
              continue

            try:
                subscriberListLocal = process_item(item,subscriberListLocal)
            finally:
                items_queue.task_done()

        except queue.Empty:
            pass
        except:
            logging.exception('error while processing item')


def process_item(newSubscriber,subscriberListLocal):
    if(len(newSubscriber)==0):
      print('processing {} started...'.format(newSubscriber))
      sys.stdout.flush()
      print("going to update users about wearther condition")
      sys.stdout.flush()
      rabbitMQ = pika.BlockingConnection(pika.ConnectionParameters(host=rabbitMQHost))
      rabbitMQChannel = rabbitMQ.channel()
      rabbitMQChannel.queue_declare(queue='toComputeEngine')
      for subscriber in subscriberListLocal: 
        cmd = subscriber.split('$')
        newCmd = "00"+"$"+cmd[2]+"$"+cmd[3]+"$"+cmd[1]
        print(newCmd)
        sys.stdout.flush()
        print("Sending update for subscribed user" + cmd[1] + " user with startLoc " + cmd[2] + " endLoc "+cmd[3])
        sys.stdout.flush()
        rabbitMQChannel.basic_publish(exchange='',routing_key='toComputeEngine', body=newCmd)
      rabbitMQChannel.close()
      rabbitMQ.close()
      return subscriberListLocal

    print('processing {} started...'.format(newSubscriber))
    sys.stdout.flush()
    time.sleep(0.5)
    print("got a subscribe/unsubscribe request")
    sys.stdout.flush()
    cmd  =  newSubscriber.split('$')
    isPresent = False
    for subscriber in subscriberListLocal:
      cmd1 = subscriber.split("$")
      if(cmd1[1] == cmd[1]):
        isPresent = True

    if(isPresent == False and cmd[0]=='01'):      
            print("got a subscribe request")
            sys.stdout.flush()
            subscriberListLocal.append(newSubscriber)
    if(isPresent == True and cmd[0]=='02'):
            subscriberListLocal.remove(subscriber)    
    print(subscriberListLocal)        
    print('processing {} done'.format(newSubscriber))
    return subscriberListLocal

def subscribe(string):
    subscriberList.append(string)
    items_queue.put(string)
    return
def unsubscribe(string):
    #subscriberList.remove(string)
    items_queue.put(string)
    return
def onWeatherChange(message):
    for subscriber in subscriberList:
       sendGmail(subscriber,adminEmailId,adminEmailPsw, message)
    return


def callback(ch, method, properties, body):
    print(datetime.datetime.now())
    
    print(" [x] Received %r" % body.decode())
    string  = body.decode('utf-8')
    cmd  =  string.split('$')
    if(cmd[0] == "01"):
      if(len(cmd)<3):
        print(" subscribe cmd is not proper, follow CMD SUBCMD ARG1 ARG2 ARG3")
      subscribe(string)
    
    if(cmd[0] == "02"):
      if(len(cmd)<2):
        print(" unsubscribe cmd is not proper, follow CMD SUBCMD ARG1 ARG2 ARG3")
      unsubscribe(string)

    if(cmd[0] == "05"):
        sendGmail(cmd[1],adminEmailId,adminEmailPsw,cmd[2])
        print(" Sending mail to subscriber "+ cmd[1])
        #onWeatherChange(cmd[2]+" "+cmd[3]+" "+cmd[4])


#
# Add code to read the persistant subscriber list from db
#

threading.Thread(target=items_queue_worker).start()
threading.Thread(target=timerThread).start()
rabbitMQ = pika.BlockingConnection(
        pika.ConnectionParameters(host='rabbitmq'))
rabbitMQChannel = rabbitMQ.channel()
rabbitMQChannel.queue_declare(queue='toSubscriberWorker')
print(' [*] Waiting for messages. To exit press CTRL+C')
rabbitMQChannel.basic_qos(prefetch_count=1)
rabbitMQChannel.basic_consume(queue='toSubscriberWorker', on_message_callback=callback,auto_ack=True)
rabbitMQChannel.start_consuming()
