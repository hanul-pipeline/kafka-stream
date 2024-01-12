from confluent_kafka import Consumer
from datetime import datetime
from threading import Thread
import gc

class KafkaConsumer:
    def __init__(self, conf:dict):
        self.conf = conf
        self.consumer_client = Consumer(conf)

class KafkaConsumerStream(KafkaConsumer):
    def __init__(self, consumer_client, topics:list):
        super().__init__(consumer_client)
        self.topics = topics
        self.consumer_client.subscribe(self.topics)

    def poll_messages(self, period:float=1.0):
        try:
            while True:
                # collect garbage & set poll
                gc.collect()
                msg = self.consumer_client.poll(period)
                if msg is None:
                    continue
                
                # run functions
                self.tasks(msg)
                
        except KeyboardInterrupt:
            pass
        
        finally:
            self.consumer_client.close()
        
    def tasks(self, msg):
        # read datas (topic, partition, key, message, nowdate)
        topic = msg.topic()
        # partition = msg.partition()
        key = msg.key().decode('utf-8') if msg.key() else None
        value = msg.value().decode('utf-8')
        nowdate = datetime.fromtimestamp(msg.timestamp()[-1]).strftime('%Y-%m-%d %H:%M:%S')
        
        # run tasks with extra threads
        threads = []
        threads.append(Thread(target = self.insert_measurement_to_mysql, args = (key, value, nowdate)))
        threads.append(Thread(target = self.define_grade, args = (topic, key, value, nowdate)))
        for thread in threads:
            thread.start()
        
    def insert_measurement_to_mysql(self, key, value, nowdate):
        from mysql_lib import execute_query
        
        # define params
        sensor_id = key
        measurement = float(value)
        insert_date = nowdate
        
        # execute insert query
        query = """
        INSERT INTO measurement
        VALUES (%s, %s, %s)
        """
        values = (sensor_id, measurement, insert_date)
        execute_query(database = "stream", query = query, values = values)

    def define_grade(self, topic, key, value, nowdate):
        from mysql_libs import fetchall_query
        
        # define params
        location_id = topic.split("_")[-1]
        sensor_id = key
        measurement = value
        insert_date = nowdate
        
        # fetchall query
        query = f"""
        SELECT type_id, grade
        FROM grade
        WHERE sensor_id = {sensor_id}
        AND {measurement} BETWEEN low_value AND top_value
        """
        (type_id, grade) = fetchall_query(database = "information", query = query)
        
        # do aftertask if alert happens
        True if grade == 'normal' \
            else self.insert_alert_to_mysql(type_id, location_id, grade, insert_date)
    
    def insert_alert_to_mysql(self, type_id, location_id, grade, insert_date):
        from mysql_libs import execute_query
        
        # execute insert query
        query = """
        INSERT INTO alert
        VALUES (%s, %s, %s, %s)
        """
        values = (type_id, location_id, grade, insert_date)
        execute_query(database = "stream", query = query, values = values)
        

if __name__ == "__main__":
    conf = {'bootstrap.servers': 'localhost:9092',         
            'group.id': 'TEST',
            'auto.offset.reset': 'earliest' }
    topics = ["test"]
    consumer = KafkaConsumerStream(conf, topics)
    consumer.poll_messages()
    