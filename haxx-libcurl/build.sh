#!/bin/bash
source $(pwd)/../openssl/find.script
./configure --prefix=$SELFHOME --with-ssl=$openssl_HOME && make -j $CORES && make -j $CORES install

