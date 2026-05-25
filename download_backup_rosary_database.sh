#!/bin/bash
#

railway ssh "cat /data/roza.db" > roza-backup-$(date +%Y%m%d).db

