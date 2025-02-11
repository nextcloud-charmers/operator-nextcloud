#!/bin/bash

juju deploy ./nextcloud-v1.0.0.charm --series=focal
juju deploy postgresql --revision 290 --channel latest/stable --series focal
juju relate postgresql:db nextcloud:db

