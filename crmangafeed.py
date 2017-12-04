#!/usr/bin/python

import os, sys
import re
import json
import time, datetime, pytz
from pprint import pprint
from operator import itemgetter
from feedgen.feed import FeedGenerator

# From https://github.com/aheadley/python-crunchyroll
from crunchyroll.apis.meta import MetaApi
from crunchyroll.models import *



DEBUG = False
BASE_CR_URL = "http://crunchyroll.com"
MANGA_URL = "http://www.crunchyroll.com/comics_read/manga?volume_id={volume_id}&chapter_num={number}"
DESTINATION_FOLDER = "../utils.senpai.moe/crmanga/"
REQUEST_WAIT_TIME = 2
LOGFILE = "crmanga.log"

CHAPTER_DATE_JSON_FILE = "chapterdates.json"
ASSUME_NO_DATE_MEANS = 'now' #now, default, skip
ASSUME_NO_DATE_MEANS_DEFAULT = "2010-01-01 00:00:00"
TRY_GET_CHAPTER_AVAIL_START = False
TRY_GET_SERIES_CREATED_DATE = False









class ChapterDateHandler(object):
	def __init__(self):
		super(ChapterDateHandler, self).__init__()
		self.data = {}
		try:
			with open(CHAPTER_DATE_JSON_FILE) as data_file:    
				self.data = json.load(data_file)
		except: pass

	def save(self):
		try:
			with open(CHAPTER_DATE_JSON_FILE, "w") as outfile:
				json.dump(self.data, outfile)
		except:
			log("Couldn't write json chapter data to file")
			raise

	def date_is_valid(self, date):
		return date and isinstance(date, basestring) and not date=="0000-00-00 00:00:00"

	def return_first_valid_date(self, dates):
		for date in dates:
			if self.date_is_valid(date):
				return date
		return None

	def get_date_now(self):
		return datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')

	def get_chapter_date(self, chapter, series):
		try:
			id = chapter.chapter_id
			if id in self.data:
				return self.data[id]
			dates = [ chapter.updated ]
			if TRY_GET_CHAPTER_AVAIL_START: dates.append( chapter.availability_start )
			if TRY_GET_SERIES_CREATED_DATE: dates.append(series.created)
			if ASSUME_NO_DATE_MEANS=="default": dates.append( ASSUME_NO_DATE_MEANS_DEFAULT )
			elif ASSUME_NO_DATE_MEANS=="now": dates.append( self.get_date_now() )
			date = self.return_first_valid_date(dates)
			if date==None:
				return None
			return date
		except:
			return None

	def save_chapter_date(self, chapter, date):
		if not self.date_is_valid(date):
			return None
		id = chapter.chapter_id
		self.data[id] = date




class CRMangaFeedException(Exception):
    pass


def log(s):
	print s
	with open(LOGFILE, 'a') as the_file:
		the_file.write('%s %s\n' % (datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), s) )






def build_manga_list(verbose=True):
	
	api = MetaApi()
	chapterdates = ChapterDateHandler()

	allchapters = []

	allseries = api._manga_api.list_series()
	if verbose:
		print "Retrieved", len(allseries), "manga titles from API"
		print
	if DEBUG: allseries = allseries[0:3]
	ctr = 0
	for series in allseries:

		try: series = Series(series)
		except: pass

		seriesname = '(seriesname_unknown)'
		try: seriesname = series.locale.enUS.name
		except: pass
		try: seriesname = seriesname.decode("utf-8").encode('ascii','ignore')
		except: pass
		try: seriesname = re.sub(r'[^\x00-\x7F]',' ', seriesname)
		except: pass

		try:
			time.sleep(REQUEST_WAIT_TIME)
			ctr += 1
			if verbose: print "["+str(ctr)+"/"+str(len(allseries))+"]", "Getting", seriesname,"..."
			chapters = api.list_chapters(series)
			for chapter in chapters:
				try:
					try: chapter = Chapter(chapter)
					except: pass
						
					date = chapterdates.get_chapter_date(chapter, series)

					allchapters.append({
						"series": series.locale.enUS.name,
						"series_id": series.series_id,
						"guid": chapter.chapter_id,
						"thumb": series.locale.enUS.thumb_url,
						"volume_id": chapter.volume_id,
						"number": chapter.number,
						"url": MANGA_URL.replace("{volume_id}",chapter.volume_id).replace("{number}",chapter.number),
						"name": chapter.locale.enUS.name,
						"updated": date,
						"updated_t": datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
					})

					chapterdates.save_chapter_date(chapter, date)
				except Exception as e:
					log("      Skipped chapter %s in series %s (%s)" % (chapter.locale.enUS.name, seriesname, str(e)) )
					pass
		except Exception as e:
			try:
				try: log("      Skipped series %s (%s)" % (seriesname, str(e)) )
				except:
					log("      Error %s" % str(e))
					log("      Also couldn't print series name")
			except:
				log("      Fatal error")

	chapterdates.save()

	return allchapters


def build_xml_feed(allchapters, verbose=True):

	if verbose:
		print
		print "Generating feeds..."

	if len(allchapters)==0: raise CRMangaFeedException("Empty chapter list")
	
	crtz = pytz.timezone('America/New_York')

	fg = FeedGenerator()
	fg.id('http://utils.senpai.moe/')
	fg.title('Crunchyroll Manga - Latest Chapters (Unofficial)')
	fg.author( {'name':'Nosgoroth','email':'nosgoroth@gmail.com'} )
	fg.link( href='http://utils.senpai.moe/' )
	fg.subtitle('Latest manga chapters, updated daily, using undocumented API.')
	fg.language('en')
	fg.ttl(15)

	allchapters = sorted(allchapters, key=itemgetter('updated_t'), reverse=True)

	first = allchapters[0]["updated_t"].replace(tzinfo=crtz)
	fg.updated( first )
	fg.lastBuildDate( first )

	for chapter in allchapters[0:100]:
		fe = fg.add_entry()
		fe.id(chapter["url"])
		fe.link({"href":chapter["url"], "rel":"alternate", "title":"Read online"})
		fe.title( "%s - %s" % (chapter["series"], chapter["name"]) )
		fe.summary( "<p>%s has been added to %s in Crunchyroll Manga.</p>" % (chapter["name"], chapter["series"]) )
		fe.published( chapter["updated_t"].replace(tzinfo=crtz) )

		chapter_serial = chapter.copy()
		chapter_serial.pop("updated_t", None)
		chapter_serial.pop("url", None)
		chapter_serial.pop("thumb", None)
		chapter_serial["chapter_id"] = chapter_serial["guid"]
		chapter_serial.pop("guid", None)

		content = "<p>%s has been added to %s in Crunchyroll Manga.</p><p>Updated: %s</p><img src=\"%s\" />" % (chapter["name"], chapter["series"], chapter["updated"], chapter["thumb"])
		content += "<!--JSON:[[%s]]-->" % json.dumps(chapter_serial)
		fe.content( content )


	fg.rss_file( os.path.join(DESTINATION_FOLDER, 'updates_rss.xml'), pretty=DEBUG) # Write the RSS feed to a file
	fg.atom_file( os.path.join(DESTINATION_FOLDER, 'updates_atom.xml'), pretty=DEBUG) # Write the ATOM feed to a file

def build_json_dump(allseries, allchapters):
	pass


if __name__ == '__main__':
	try:
		log("CR Manga feed update starts")
		allchapters = build_manga_list()
		build_xml_feed(allchapters)
		log("CR Manga feed updated successfully!")
	except KeyboardInterrupt:
		pass
	except CRMangaFeedException, e:
		log("CR Manga feed errored out! Error: "+str(e))
		pass
	except:
		log("CR Manga feed errored out!")
		raise
