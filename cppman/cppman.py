#-*- coding: utf-8 -*-
# 
# cppman.py 
#
# Copyright (C) 2010 -  Wei-Ning Huang (AZ) <aitjcize@gmail.com>
# All Rights reserved.
#
# This file is part of manpages-cpp.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

import gzip
import os
import os.path
import re
import shutil
import sqlite3
import subprocess
import urllib

import Environ
import Formatter
from Crawler import Crawler

class cppman(Crawler):
    '''
    Manage cpp man pages, indexes
    '''
    def __init__(self, forced=False):
        Crawler.__init__(self)
        self.forced = forced

    def extract_name(self, data):
        '''
        Extract man page name from cplusplus web page.
        '''
        name = re.search('<h1>(.+?)</h1>', data).group(1)
        name = re.sub(r'<([^>]+)>', r'', name)
        name = re.sub(r'&gt;', r'>', name)
        name = re.sub(r'&lt;', r'<', name)
        return name

    def rebuild_index(self):
        '''
        Rebuild index database from cplusplus.com
        '''
        try:
            os.remove(Environ.index_db)
        except: pass
        self.db_conn = sqlite3.connect(Environ.index_db)
        self.db_cursor = self.db_conn.cursor()
        self.db_cursor.execute('CREATE TABLE CPPMAN (name VARCHAR(255), '
                               'url VARCHAR(255))')
        self.crawl(self.insert_index)
        
        # Rename dumplicate entries
        dumplicates = self.db_cursor.execute('SELECT name, COUNT(name) AS NON '
                                             'FROM CPPMAN '
                                             'GROUP BY NAME '
                                             'HAVING (NON > 1)').fetchall()
        for name, url in dumplicates:
            dump = self.db_cursor.execute('SELECT name, url FROM CPPMAN '
                                          'WHERE name="%s"' % name).fetchall()
            for n, u in dump:
                if not 'clibrary' in u:
                    new_name = re.search('/([^/]+)/%s/' % n,
                                         u).group(1) + '::' + n
                    self.db_cursor.execute('UPDATE CPPMAN '
                                           'SET name="%s", url="%s" '
                                           'WHERE url="%s"' % (new_name, u, u))
        self.db_conn.commit()
        self.db_conn.close()

    def insert_index(self, url):
        '''
        callback to insert index
        '''
        name = self.extract_name(urllib.urlopen(url).read())
        self.db_cursor.execute('INSERT INTO CPPMAN (name, url) VALUES '
                               '("%s", "%s")' % (name, url))

    def cache_all(self):
        '''
        Cache all available man pages from cplusplus.com to 
        '''
        print 'By defualt, cppman fetch pages on the fly if coressponding '\
            'page is not found in the cache. The "cache-all" option is only '\
            'useful if you want to view man pages offline.'
        print 'Caching all contents from cplusplus.com could take a LONG '\
            'time, do you want to continue [Y/n]?',

        respond = raw_input()
        if respond.lower() not in ['y', 'ye', 'yes']:
            print 'Aborted.'
            return

        try:
            os.mkdir(Environ.man_dir)
        except: pass
        self.crawl(self.cache_man_page)

    def cache_man_page(self, url, name=None):
        '''
        callback to cache new man page
        '''
        data = urllib.urlopen(url).read()
        groff_text = Formatter.cplusplus2groff(data)
        if not name: name = self.extract_name(data)

        # Skip if already exists, override if forced flag is true
        outname = Environ.man_dir + name + '.3.gz'
        if os.path.exists(outname) and not self.forced:
            return
        f = gzip.open(outname, 'w')
        f.write(groff_text)
        f.close()

    def clear_cache(self):
        '''
        Clear all cache in man3
        '''
        shutil.rmtree(Environ.man_dir)

    def man(self, pattern):
        '''
        Call viewer.sh to view man page
        '''
        try:
            os.mkdir(Environ.man_dir)
        except: pass

        avail = subprocess.Popen('ls %s' % Environ.man_dir, shell=True,
                                 stdout=subprocess.PIPE).stdout.read().split()
        conn = sqlite3.connect(Environ.index_db)
        cursor = conn.cursor()

        # Try direct match
        try:
            page_name, url = cursor.execute('SELECT name,url FROM CPPMAN WHERE'
                                ' name="%s"' % pattern).fetchone()
        except TypeError:
            # Try ambiguous search
            try:
                page_name, url = cursor.execute('SELECT name,url FROM CPPMAN'
                            ' WHERE name LIKE "%%%s%%"' % pattern).fetchone()
            except TypeError:
                raise RuntimeError('No manual entry for ' + pattern)
        finally:
            conn.close()

        if page_name + '.3.gz' not in avail or self.forced:
            self.cache_man_page(url, page_name)

        # Call viewer
        pid = os.fork()
        if pid == 0:
            os.execl(Environ.viewer, 'dummy',
                     Environ.man_dir + page_name + '.3.gz',
                     str(Formatter.get_width()))
        return pid

    def find(self, pattern):
        conn = sqlite3.connect(Environ.index_db)
        cursor = conn.cursor()
        selected = cursor.execute('SELECT name,url FROM CPPMAN'
                            ' WHERE name LIKE "%%%s%%"' % pattern).fetchall()
        if selected:
            for name, url in selected:
                print re.sub(pattern, '\033[1;31m%s\033[0m' % pattern, name)
        else:
            raise RuntimeError('%s: nothing appropriate.' % pattern)
