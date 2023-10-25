import random
import logging
import traceback
import maxwell.protocol.maxwell_protocol_pb2 as protocol_types

from .config import Config
from .connection import Connection, Code, Event, MaxwellError
from .topic_locatlizer import TopicLocatlizer

logger = logging.getLogger(__name__)


class Publisher(object):
    # ===========================================
    # apis
    # ===========================================
    def __init__(self, options, loop):
        self.__options = options
        self.__loop = loop

        self.__topic_locatlizer = TopicLocatlizer(self.__loop)
        self.__connections = {}  # endpoint => [connection0, connection1, ...]
        self.__continuous_disconnected_times = 0

    def __del__(self):
        self.close()

    def close(self):
        for connections in self.__connections.values():
            for connection in connections:
                connection.close()
        self.__topic_locatlizer.close()

    async def publish(self, topic, value):
        try:
            connection = await self.__get_connetion(topic)
            await connection.wait_open()
            return await connection.request(self.__build_publish_req(topic, value))
        except Exception as e:
            logger.error(
                "Failed to publish: msg: %s, trace: %s", e, traceback.format_exc()
            )

    # ===========================================
    # internal functions
    # ===========================================

    async def __get_connetion(self, topic):
        endpoint = await self.__topic_locatlizer.locate(topic)
        connections = self.__connections.get(endpoint)
        size = Config.singleton().get_connection_slot_size()
        if connections is None:
            connections = []
            for _ in range(size):
                connection = Connection(endpoint, self.__options, self.__loop)
                connection.add_listener(
                    event=Event.ON_DISCONNECTED,
                    callback=self.__on_disconnected_to_backend,
                )
                connections.append(connection)
            self.__connections[endpoint] = connections
        return connections[random.randint(0, size - 1)]

    def __on_disconnected_to_backend(self, connection):
        self.__continuous_disconnected_times += 1
        if (
            self.__continuous_disconnected_times
            >= Config.singleton().get_max_continuous_disconnected_times()
        ):
            self.__continuous_disconnected_times = 0
            self.__connections.pop(connection.get_endpoint(), None)

    def __build_publish_req(self, topic, value):
        push_req = protocol_types.push_req_t()
        push_req.topic = topic
        push_req.value = value
        return push_req
