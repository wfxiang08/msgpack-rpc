from mprpc.rpc import future
from mprpc.rpc import transport

class Session:
    """
    Session processes send/recv request of the message, by using underlying
    transport layer.

    self._req_table stores the relationship between messageid and corresponding
    future. When the new requets are sent, the Session generates new message id
    and new future. Then the Session registers them to req_table.

    When it receives the message, the Session lookups the req_table and set the
    result to the corresponding future.
    """

    def __init__(self, addr, loop):
        self._addr = addr
        self._loop = loop
        self._req_table = {}
        self._transport = None

    def get_addr(self):
        return self._addr

    def send_request(self, method, args):
        """Sends the request to the remote MessagePack-RPC server. This takes
        the following steps.
        (1) Generates the new message id and the new future.
        (2) Registers them to the req_table.
        (3) Passes the message to the underlying transport layer
        """
        f = future.Future(self._loop)
        msgid = self._gen_msgid()
        self._req_table[msgid] = f

        transport = self._get_transport()
        transport.send_message([0, msgid, method, args])
        return f

    def try_close(self):
        if (self._transport != None):
            self._transport.try_close()
        self._transport = None

    _msgid_counter = 0

    def _gen_msgid(self):
        """Generates new message id, from the global counter"""
        msgid = self._msgid_counter
        self._msgid_counter = self._msgid_counter + 1
        if self._msgid_counter > (1 << 30):
            self._msgid_counter = 0
        return msgid

    def _get_transport(self):
        """Creates new transport when it's not available"""
        if self._transport != None:
            return self._transport
        self._transport = transport.TCPTransport(self, self._loop)
        return self._transport

    def _cb_connect_failed(self, reason):
        """The callback called when the connection failed.
        Called by the transport layer.
        """
        # set error for all requests
        for msgid, future in self._req_table.items():
            future.set_error(reason)
        self._req_table = {}
        self.try_close()
        self._loop.stop()

    def _cb_msg_received(self, msg):
        """The callback called when the message arrives.
        Called by the transport layer.
        """
        if len(msg) != 4:
            raise Exception("invalid mprpc protocol")
        msgtype = msg[0]
        msgid   = msg[1]
        msgerr  = msg[2]
        msgret  = msg[3]
        if (msgtype != 1):
            raise Exception("invalid mprpc protocol")

        # lookup msgid in req_table
        if not msgid in self._req_table:
            raise Exception("unknown msgid")
        future = self._req_table[msgid]
        del self._req_table[msgid]

        # set value to the future
        if msgerr != None:
            future.set_error(msgerr)
        else:
            future.set_result(msgret)
        self._loop.stop()

    def _cb_closed(self, reason):
        """The callback called when the connection closed.
        Called by the transport layer.
        """
        # set error for all requests
        for msgid, future in self._req_table.items():
            future.set_error(reason)
        self._req_table = {}
        self.try_close()
        self._loop.stop()

    def _cb_failed(self):
        """The callback called when the error occurred.
        Called by the transport layer.
        """
        # set error for all requests
        for msgid, future in self._req_table.items():
            future.set_error("failed")
        self._req_table = {}
        self.try_close()
        self._loop.stop()
