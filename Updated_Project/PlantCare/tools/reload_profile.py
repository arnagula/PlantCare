"""Privileged operator operation; file path is fixed per mode, never supplied by a browser."""
import argparse
from aws.handler import enqueue,profile
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['live','simulated']);a=p.parse_args()
 enqueue(a.mode,'reload',profile(a.mode))
 print('Reload queued. Confirm profile_revision on /api/state; busy reloads are rejected and journaled.')
