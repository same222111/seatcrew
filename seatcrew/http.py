"""Local HTTP services must start without waiting for network name resolution."""
from http.server import ThreadingHTTPServer
from socketserver import TCPServer


class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind calls getfqdn even for 127.0.0.1. Some macOS
        # resolver configurations spend a minute there. We do not serve CGI or
        # use a canonical DNS name, so the actual bind address is sufficient.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]
