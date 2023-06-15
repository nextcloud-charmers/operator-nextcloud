# import sys
import os
import unittest
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
# sys.path.append('./src')
import utils


class TestUtils(unittest.TestCase):
    """
    Unittests for utils functions
    """

    def setUp(self) -> None:
        """
        Launch a local webserver to serve a fake nextcloud.tar.bz2 file
        :return:
        """
        os.chdir('tests')
        handler = SimpleHTTPRequestHandler
        httpd = HTTPServer(("", 8081), handler)
        self.httpd_thread = threading.Thread(target=httpd.serve_forever)
        self.httpd_thread.daemon = True
        self.httpd_thread.start()

    def tearDown(self) -> None:
        pass

    def test_fetch_and_extract_nextcloud(self) -> None:
        """
        Test fetching a tarfile containing an empty nextcloud and extract it.
        """
        utils.fetch_and_extract_nextcloud('http://localhost:8081/nextcloud.tar.bz2')


if __name__ == '__main__':
    unittest.main()
