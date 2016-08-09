#!/usr/bin/env python3

'''
A script for getting a corpus of "Onion-like" albeit real news articles.
'''

import os
import sys
import newspaper
import random
import requests
import requests.auth
import string
import time

from urllib.parse import urlsplit

DEFAULT_REQUEST_CHARSET = "UTF-8"

URL_FILENAME_TRANSLATION_TABLE = {ord(':') : '-', ord('/') : os.path.sep, ord('\\') : '-', ord('*') : '-', ord('?') : '-', ord('"') : '\'', ord('<') : '-', ord('>') : '-', ord('|') : '-', ord('\0') : '0', ord('.') : os.path.sep}

__AUTHOR_REDDIT_USERNAME = "errantlinguist"
__CLIENT_ID = "nottheonion-scraper"
__VERSION = "0.0.1"
__WEBSITE = "https://github.com/errantlinguist/nottheonion-scraper"

'''
See: https://github.com/reddit/reddit/wiki/API#user-content-rules
'''
__USER_AGENT_STR = "%(platform)s:%(app_id)s:%(version)s (by /u/%(reddit_username)s)" % {"platform" : sys.platform, "app_id" : __CLIENT_ID, "version" : __VERSION, "reddit_username" : __AUTHOR_REDDIT_USERNAME}


class AuthData(object):
	def __init__(self, auth_token_response):
		self.json = auth_token_response.json()
		self.token_type = self.json["token_type"]
		self.access_token = self.json["access_token"]
		self.auth_expiration_time = time.time() + int(self.json["expires_in"])

def create_url_filename(url_str):
	'''
	http://stackoverflow.com/a/7406369/1391325
	'''
	split_url = urlsplit(url_str)
	stripped_url_str = "".join(part for part in split_url[1:3])
	result = stripped_url_str.translate(URL_FILENAME_TRANSLATION_TABLE)
	if result.endswith(os.path.sep):
		result = result[:len(result) - len(os.path.sep)]
	return result
	
def refresh_auth_token(refresh_token, auth):
	post_data = {"grant_type": "refresh_token", "refresh_token" : refresh_token}
	headers = {
		"User-Agent" : __USER_AGENT_STR
	}
	return requests.post("https://www.reddit.com/api/v1/access_token", auth=auth, data=post_data, headers=headers)	
	
def retrieve_auth_token(auth):
	post_data = {"grant_type": "client_credentials"}
	headers = {
		"User-Agent" : __USER_AGENT_STR
	}
	return requests.post("https://www.reddit.com/api/v1/access_token", auth=auth, data=post_data, headers=headers)
	
def save_pages(url_articles, outpath_prefix):
	for url, article in url_articles.items():
		outpath_infix = create_url_filename(url)
		outpath = os.path.join(outpath_prefix, outpath_infix)
		if os.path.exists(outpath):
			print("File path \"%s\" already exists; Skipping." % outpath, file=sys.stderr)
		else:
			#print("Downloading article \"%s\"." % url, file=sys.stderr)
			article.download()
			try:
				article.parse()
			except newspaper.ArticleException as e:
				if article.is_downloaded:
					raise e
				else:
					print("Downloading the article for URL \"%s\" was not successful; Trying to download again." % url, file=sys.stderr)
					
			# After getting the response data, write it to file
			outdir = os.path.dirname(outpath)
			if not os.path.exists(outdir):
				os.makedirs(outdir)
			with open(outpath, 'w') as outf:
				outf.write(article.html)
			
			# Write the stripped contents to a text file
			with open(outpath + ".txt", 'w') as outf:
				outf.write(article.text)
				
			print("%s > %s" %(url, outpath), file=sys.stderr)
			
					
					
		
def scrape_reddit_thing_urls_from_response(response):
	data = response.json()["data"]
	reddit_thing_urls = scrape_reddit_thing_urls(data)
	last_thing_name = data["after"]
	return reddit_thing_urls, last_thing_name

def scrape_reddit_thing_urls(data):
	children = data["children"]
	#print("Processing %d child(ren)." % len(children))
	for child in children:
		child_data = child["data"]
		child_name = child_data["name"]
		url_attr = "url"
		url = child_data.get(url_attr)
		if url:
			yield (child_name, url)
		else:
			print("Reddit thing named \"%s\" has no \"%s\" attribute." %(child_name, url_attr), file=sys.stderr)
			
		
if __name__ == "__main__":
	if len(sys.argv) != 3:
		print("Usage: %s REDDIT_APP_SECRET OUTDIR" % sys.argv[0], file=sys.stderr)
		sys.exit(64)
	else:
		# Oauth2 authentication <https://github.com/reddit/reddit/wiki/OAuth2#user-content-authorization>
		# https://github.com/reddit/reddit/wiki/OAuth2-Quick-Start-Example#user-content-python-example
		secret = sys.argv[1]
		auth=("_JNFnqor9ZT4mQ", secret)
		auth_token_response = retrieve_auth_token(auth)
		auth_token_response.raise_for_status()
		auth_data = AuthData(auth_token_response)
		
		
		params = {"limit" : 100}
		while auth_token_response:
			url_articles = {}
			if auth_data.auth_expiration_time <= time.time():
				print("Refreshing authentication token.", file=sys.stderr)
				auth_token_response = refresh_auth_token(auth_data.access_token, auth)
				auth_token_response.raise_for_status()
				auth_data = AuthData(auth_token_response)
				
			headers = {
				"Accept" : "application/json",
				"Accept-Charset" : DEFAULT_REQUEST_CHARSET,
				"Authorization": auth_data.token_type + " " + auth_data.access_token,
				"User-Agent": __USER_AGENT_STR}
			next_page_response = requests.get("https://oauth.reddit.com/r/nottheonion/.json", headers=headers, params=params)
			try:
				next_page_response.raise_for_status()
			except HTTPError:
				if next_page_response.status_code == 403:
					print("Refreshing authentication token.", file=sys.stderr)
					auth_token_response = refresh_auth_token(auth_data.access_token, auth)
					auth_token_response.raise_for_status()
					auth_data = AuthData(auth_token_response)
					
				
			reddit_thing_urls, last_thing_name = scrape_reddit_thing_urls_from_response(next_page_response)
			urls = (url for name, url in reddit_thing_urls)
			for url in urls:
				#print("Adding URL \"%s\" to batch." % url, file=sys.stderr)
				article = newspaper.Article(url, follow_meta_refresh=False, keep_article_html=True)
				url_articles[url] = article
			
			print("Retrieving %d articles." % len(url_articles), file=sys.stderr)
			outdir = sys.argv[2]
			save_pages(url_articles, outdir)
			
			if last_thing_name:
				params["count"] += len(url_articles)
				params["after"] = last_thing_name
			else:
				break
				
		print("Retrieved %d articles in total." % params["count"], file=sys.stderr)
		
		
