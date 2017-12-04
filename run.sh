#!/bin/bash

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
cd $DIR

export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8

LC_ALL=en_US.UTF-8
LANG=en_US.UTF-8

source ./env/bin/activate
python crmangafeed.py
deactivate
