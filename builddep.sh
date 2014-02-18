#!/bin/bash

if [[ $BUILD_FROM_SOURCE ]]; then
    sudo apt-get install -qq build-essential cmake uuid-dev
    wget http://www.taskwarrior.org/download/task-$TASK_VERSION.tar.gz
    tar -zxvf task-$TASK_VERSION.tar.gz
    cd task-$TASK_VERSION
    cmake .
    make
    sudo make install
else
    sudo apt-get install task=$TASK_VERSION
fi
