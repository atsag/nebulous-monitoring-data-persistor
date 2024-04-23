import logging
import sys
import threading
from jproperties import Properties

from influxdb_client import Point, WritePrecision

import exn
from main.runtime.Constants import Constants
from main.runtime.InfluxDBConnector import InfluxDBConnector
from exn import connector, core
from exn.core.handler import Handler
from exn.handler.connector_handler import ConnectorHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger('main.exn.connector').setLevel(logging.DEBUG)


class Bootstrap(ConnectorHandler):
    pass
class ConsumerHandler(Handler):
    influx_connector = InfluxDBConnector()
    application_name = ""
    def __init__(self,application_name):
        self.application_name = application_name
    def on_message(self, key, address, body, context, **kwargs):
        logging.info(f"Received {key} => {address}")
        if ((str(address)).startswith(Constants.monitoring_prefix) and not (str(address)).endswith(Constants.metric_list_topic)):
            logging.info("New monitoring data arrived at topic "+address)
            logging.info(body)
            point = Point(str(address).split(".")[-1]).field("metricValue",body["metricValue"]).tag("level",body["level"]).tag("application_name",self.application_name)
            point.time(body["timestamp"],write_precision=WritePrecision.MS)
            logging.info("Writing new monitoring data to Influx DB")
            self.influx_connector.write_data(point,self.application_name)

class GenericConsumerHandler(Handler):
    connector_thread = None
    initialized_connector = None
    application_consumer_handler_connectors = {} #dictionary in which keys are applications and values are the consumer handlers.

    def GenericConsumerHandler(self):
        if self.connector_thread is not None:
            self.initialized_connector.stop()
    def on_message(self, key, address, body, context, **kwargs):

        if (str(address)).startswith(Constants.monitoring_prefix+Constants.metric_list_topic):
            application_name = body["name"]
            logging.info("New metrics list message for application "+application_name + " - registering new connector")
            if (application_name in self.application_consumer_handler_connectors.keys()  is not None):
                logging.info("Stopping the old existing connector...")
                self.application_consumer_handler_connectors[application_name].stop()
            logging.info("Attempting to register new connector...")
            from time import sleep
            sleep(10)
            self.initialized_connector = exn.connector.EXN(
                Constants.data_persistor_name + "-" + application_name, handler=Bootstrap(),
                consumers=[
                    core.consumer.Consumer('monitoring',
                        Constants.monitoring_broker_topic + '.realtime.>',
                        application=application_name,
                        topic=True,
                        fqdn=True,
                        handler=ConsumerHandler(application_name=application_name)
                    ),
                ],
                url=Constants.broker_ip,
                port=Constants.broker_port,
                username=Constants.broker_username,
                password=Constants.broker_password
            )
            logging.info("Connector ready to be registered")
            #connector.start()
            self.application_consumer_handler_connectors[application_name] = self.initialized_connector
            logging.info(f"Application specific connector registered for application {application_name}")
            self.initialized_connector.start()
            logging.info(f"Application specific connector started for application {application_name}")
        #If threading support is explicitly required, uncomment these lines
            #connector_thread = threading.Thread(target=self.initialized_connector.start,args=())
            #connector_thread.start()
            #connector_thread.join()

def update_properties(configuration_file_location):
    p = Properties()
    with open(configuration_file_location, "rb") as f:
        p.load(f, "utf-8")
        Constants.db_hostname, metadata = p["db_hostname"]
        Constants.broker_ip, metadata = p["broker_ip"]
        Constants.broker_port, metadata = p["broker_port"]
        Constants.broker_username, metadata = p["broker_username"]
        Constants.broker_password, metadata = p["broker_password"]
        Constants.monitoring_broker_topic, metadata = p["monitoring_broker_topic"]
        Constants.organization_name,metadata = p["organization_name"]
        Constants.bucket_name,metadata = p["bucket_name"]

def main():
    Constants.configuration_file_location = sys.argv[1]
    update_properties(Constants.configuration_file_location)
    component_handler = Bootstrap()

    connector_instance = connector.EXN(Constants.data_persistor_name, handler=component_handler,
                                       consumers=[
                                  core.consumer.Consumer('monitoring_data', Constants.monitoring_broker_topic + '.>', topic=True, fqdn=True, handler=GenericConsumerHandler()),
                              ],
                                       url=Constants.broker_ip,
                                       port=Constants.broker_port,
                                       username=Constants.broker_username,
                                       password=Constants.broker_password
                                       )
    #connector.start()
    thread = threading.Thread(target=connector_instance.start,args=())
    thread.start()

    print("Waiting for messages at the metric list topic, in order to start receiving applications")

if __name__ == "__main__":
    main()