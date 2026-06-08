import ssl
import socket
import pprint

context = ssl._create_unverified_context()
try:
    with socket.create_connection(("240.0.0.2", 443), timeout=3.0) as sock:
        with context.wrap_socket(sock, server_hostname="googleapis.com") as ssock:
            cert = ssock.getpeercert()
            print("Subject:")
            pprint.pprint(cert.get('subject'))
            print("\nSubject Alternative Name (SAN):")
            pprint.pprint(cert.get('subjectAltName'))
except Exception as e:
    print("Error fetching certificate:", e)
