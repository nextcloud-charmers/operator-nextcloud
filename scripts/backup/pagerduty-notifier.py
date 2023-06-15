#! /usr/bin/python3
import argparse
from pdpyras import APISession


def main(args):
    session = APISession(args.token, default_from=args.from_email)

    payload = {
        "incident": {
            "type": "incident",
            "title": "Backup failed!",
            "service": {
                "id": args.service_id,
                "type": "service_reference"
            },
            "body": {
                "type": "incident_body",
                "details": args.message
            }
        }
    }
    session.rpost("incidents", json=payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Send an alarm to PagerDuty')
    parser.add_argument('-m', '--message', type=str, required=True, help='The message to post')
    parser.add_argument('-t', '--token', type=str, required=True, help='API token from PagerDuty.')
    parser.add_argument('-e', '--from-email', type=str, required=True, help='The email for the PagerDuty account.')
    parser.add_argument('-s', '--service-id', type=str, required=True, help='PagerDuty service ID.')
    args = parser.parse_args()
    print(args)

    main(args)
