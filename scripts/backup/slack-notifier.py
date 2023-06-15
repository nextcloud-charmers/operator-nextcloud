#! /usr/bin/python3
import argparse
import requests


def main(args):
    data = {'text': args.message}
    r = requests.post(args.webhook_url, json=data)
    if r.status_code != 200:
        raise Exception("Did not get response code OK:", r.text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Send a message to the specified Slack webhook. \
        More information about webhooks can be found at https://api.slack.com/messaging/webhooks')
    parser.add_argument('-m', '--message', required=True, type=str, help='the message to post')
    parser.add_argument('-w', '--webhook_url', type=str, required=True, help='the webhook-url to post to')
    args = parser.parse_args()
    print(args)

    main(args)
