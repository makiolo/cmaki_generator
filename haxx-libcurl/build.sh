#!/bin/bash
./configure --prefix=$SELFHOME --with-ssl && make -j $CORES && make -j $CORES install

