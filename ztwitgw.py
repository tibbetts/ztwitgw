#!/usr/bin/python

"""take recent twitters and zephyr them to me"""

import urllib
import simplejson
import sys
import os
import getpass
import subprocess
import time
import errno

urllib.URLopener.version = "thok.org-ztwitgw.py-one-way-zephyr-gateway/0.1"

# from comick.py - either I should come up with my *own* library
#  for this, or find some existing library that has come out since
#  2003 that already does (maybe pycurl...)
class MyFancyURLopener(urllib.FancyURLopener):
    """prevent implicit basicauth prompting"""
    http_error_default = urllib.URLopener.http_error_default
    # don't allow password prompts
    prompt_user_passwd = lambda self, host, realm: (None, None)

def get_changed_content(url, etag=None, lastmod=None):
    """get changed content based on etag/lastmod"""
    uo = MyFancyURLopener()
    if etag:
        uo.addheader("If-None-Match", etag)
    if lastmod:
        uo.addheader("If-Modified-Since", lastmod)
    try:
        u = uo.open(url)
    except IOError, e:
        if e[0] == "http error" and e[1] == 304:
            return None, None, None
        raise
    if u.headers.has_key("ETag"):
        etag = u.headers["ETag"]
    if u.headers.has_key("Last-Modified"):
        lastmod = u.headers["Last-Modified"]
    s = u.read()
    u.close()
    return (s, etag, lastmod)

twit_url = "http://twitter.com/statuses/friends_timeline.json"
replies_url = "http://twitter.com/statuses/replies.json"
def embed_basicauth(url, user, passwd):
    """stuff basicauth username/password into a url"""
    # could use urllib2 and a real basicauth handler...
    # but the url is constant, so be lazy.
    assert url.startswith("http://")
    tag, path = url.split("://", 1)
    return tag + "://" + user + ":" + passwd + "@" + path

assert "http://a:b@c/" == embed_basicauth("http://c/", "a", "b")

def embed_since_id(url, since_id):
    """add a since_id argument"""
    # http://apiwiki.twitter.com/REST+API+Documentation#statuses/friendstimeline
    assert "?" not in url, "add support for merging since_id with other url args!"
    return url + "?since_id=%s" % since_id + "&source=twitterandroid"

def zwrite(username, body, tag):
    zwrite_ci("twitter2c", username, username, body, tag)

def zwrite_mine(username, body, tag):
    zwrite_ci(getpass.getuser(), "twitter", username, body, tag) 
    
def zwrite_ci(clazz, instance, username, body, tag):
    """deliver one twitter message to zephyr"""
    # username... will get encoded when we see one
    body = body.encode("iso-8859-1", "xmlcharrefreplace")
    # tag is from codde
    cmd = ["zwrite",
           "-q", # quiet
           "-d", # Don't authenticate
           "-s", "%s %s%svia ztwitgw" % (username, tag, tag and " "),
           "-c", clazz,
           "-i", instance,
           "-m", body]
    subprocess.call(cmd)
           
def entity_decode(txt):
    """decode simple entities"""
    # TODO: find out what ones twitter considers defined,
    #   or if sgmllib.entitydefs is enough...
    return txt.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")

# turns out we don't actually see &amp; in practice...
assert entity_decode("-&gt; &lt;3") == "-> <3"

def process_new_twits(url=twit_url, tag=""):
    """process new messages, stashing markers"""
    filebase = os.path.expanduser("~/.ztwit_")
    username, pw = file(filebase + "auth", "r").read().strip().split(":", 1)
    if tag:
        filebase = filebase + tag + "_"
    lastfile = filebase + "last"
    etag = None
    lastmod = None
    if os.path.exists(lastfile):
        etag, lastmod = file(lastfile, "r").read().splitlines()

    newurl = embed_basicauth(url, username, pw)
    
    sincefile = filebase + "since"
    since_id = None
    if os.path.exists(sincefile):
        since_id = file(sincefile, "r").read().strip()
        if since_id: # allow for truncated file
            newurl = embed_since_id(newurl, since_id)

    try:
        rawtwits, etag, lastmod = get_changed_content(newurl, etag, lastmod)
    except IOError, ioe:
        if ioe[0] == "http error":
            # "http error" would be enough, given http_error_default, except
            # that open_http gives a 1-arg one if host is empty...
            try:
                (kind, code, message, headers) = ioe
            except IndexError:
                raise ioe
            if 500 <= code <= 599:
                print >> sys.stderr, code, message, "-- sleeping"
                time.sleep(90)
                sys.exit()
            else:
                raise
        elif ioe[0] == "http protocol error":
            # IOError: ('http protocol error', 0, 'got a bad status line', None)
            print >> sys.stderr, ioe, "-- sleeping"
            time.sleep(90)
            sys.exit()
        elif IOError.errno == errno.ETIMEDOUT:
            # IOError: [Errno socket error] (110, 'Connection timed out')
            print >> sys.stderr, ioe, "-- sleeping longer"
            time.sleep(90)
            sys.exit()
        # got one of these, but that should imply a bug on my side?
        # IOError: ('http error', 400, 'Bad Request', <httplib.HTTPMessage instance at 0xb7b48d0c>)
        # this one is special too...
        # IOError: ('http error', 404, 'Not Found', <httplib.HTTPMessage instance at 0xb7ad5eec>)
        else:
            raise
    if not rawtwits:
        return # nothing new, don't update either
    twits = simplejson.loads(rawtwits)
    for twit in reversed(twits):
        who = twit["user"]["screen_name"]
        what = entity_decode(twit["text"])
        if (who == "tibbetts"):
            zwrite_mine(who, what, tag)
        else:
            zwrite(who, what, tag)
        since_id = twit["id"]
            
    newlast = file(lastfile, "w")
    print >> newlast, etag
    print >> newlast, lastmod
    newlast.close()

    newsince = file(sincefile, "w")
    print >> newsince, since_id
    newsince.close()

if __name__ == "__main__":
    prog, = sys.argv
    process_new_twits()
    process_new_twits(url=replies_url, tag="reply")
