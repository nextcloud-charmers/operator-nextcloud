#!/bin/sh
#
# Generate self signed certs for hostname -f
#
# Generate self signed root CA cert
openssl req -nodes -x509 -newkey rsa:2048 -keyout ca.key -out ca.crt -subj "/C=SE/ST=STO/L=Stockholm/O=haproxy/OU=root/CN=`hostname -f`/emailAddress=info@dwellir.com"


# Generate server cert to be signed
openssl req -nodes -newkey rsa:2048 -keyout server.key -out server.csr -subj "/C=SE/ST=STO/L=Stockholm/O=haproxy/OU=server/CN=`hostname -f`/emailAddress=info@dwellir.com"

# Sign the server cert
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt

# Create server PEM file
cat server.key server.crt > server.pem


# Generate client cert to be signed
openssl req -nodes -newkey rsa:2048 -keyout client.key -out client.csr -subj "/C=SE/ST=STO/L=Stockholm/O=haproxy/OU=client/CN=`hostname -f`/emailAddress=info@dwellir.com"

# Sign the client cert
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAserial ca.srl -out client.crt

# Create client PEM file
cat client.key client.crt > client.pem


# Create clientPFX file (for Java, C#, etc)
# openssl pkcs12 -inkey client.key -in client.crt -export -out client.pfx

