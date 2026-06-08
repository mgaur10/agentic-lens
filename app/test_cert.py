import socket
import ssl

context = ssl._create_unverified_context()
try:
    with socket.create_connection(("240.0.0.2", 443), timeout=5.0) as sock:
        with context.wrap_socket(sock, server_hostname="googleapis.com") as ssock:
            cert_der = ssock.getpeercert(binary_form=True)
            cert_pem = ssl.DER_cert_to_PEM_cert(cert_der)
            print("PEM certificate:")
            print(cert_pem)
            with open("fetched_cert.pem", "w") as f:
                f.write(cert_pem)
            print("Saved to fetched_cert.pem")
except Exception as e:
    print("Error:", e)
