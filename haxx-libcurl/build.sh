#!/bin/bash
./configure --prefix=$SELFHOME --without-ssl && make -j $CORES && make -j $CORES install

