#-*- coding: utf-8 -*-
# 
# Formatter.py - format html from cplusplus.com to groff syntax
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

import datetime
import fcntl
import re
import struct
import subprocess
import sys
import termios
import urllib

# Format replacement RE list
# The '.SE' pseudo macro is described in function: cplusplus2groff
rps = [
        # Header, Name
        (r'<div class="doctop"><h1>(.+?)</h1><div class="right"><br>(.*?)</div>'
         r'</div><div class="docsubtop"><div class="right"><code>(.*)</code>'
         r'</div>\n<div class="prototype">(.*)</div>\n</div>'
         r'<p><strong>(.+?)</strong></p>\n</div><div id="content">(.+?)<br>',
         r'.TH "\1" 3 "%s" "cplusplus.com" "C++ Programmer\'s Manual"\n'
         r'\n.SH NAME\n\1 - \5\n'
         r'\n.SE\n.SH TYPE\n\2\n'
         r'\n.SE\n.SH SYNOPSIS\n#include \3\n.sp\n\4\n'
         r'\n.SE\n.SH DESCRIPTION\n\6\n.sp\n'% datetime.date.today(),re.DOTALL),
        # Remove empty sections
        (r'\n.SH (.+?)\n\n', r'', 0),
        # Section headers
        (r'.*<h3>(.+?)</h3>', r'\n.SE\n.SH "\1"\n', 0),
        # 'ul' tag
        (r'<ul>', r'\n.in +2n\n.sp\n', 0),
        (r'</ul>', r'\n.in\n', 0),
        # 'li' tag
        (r'<li>(.+?)</li>', r'* \1\n.sp\n', 0),
        # 'code' tag
        (r'<code>', r'\n.in +2n\n.sp\n', 0),
        (r'</code>', r'\n.in\n.sp\n', 0),
        # 'samp' tag
        (r'<samp>(.+?)</samp>', r'\n.nf\n\1\n.fi\n', re.DOTALL),
        # 'pre' tag
        (r'<pre\s*>(.+?)</pre\s*>', r'\n.nf\n\1\n.fi\n', re.DOTALL),
        # Subsections
        (r'<b>(.+?)</b>:<br>', r'.SS \1\n', 0),
        # Member functions / See Also table
        (r'<table class="keywordlink"><tr><td.+?>(.+?)</td><td.+?>(.+?)'
         r'<span class="typ">(.+?)</span></td></tr></table>',
         r'\n.IP "\1(3)"\n\2 \3\n', 0),
        # Three-column table
        (r'<table class="boxed">\s*<tr><th>(.+?)</th><th>(.+?)</th><th>(.+?)'
         r'</th></tr>((.|\n)+?)</table>',
         r'\n.TS\nallbox tab(|);\nc c\nl lx l .\n\1|\2|\3\n\4\n.TE\n.sp\n', 0),
        (r'<tr><td>(.+?)</td><td>(.+?)</td><td>(.+?)</td></tr>',
         r'\1|T{\n\2\nT}|T{\n\3\nT}\n', 0),
        # Two-column table
        (r'<table class="boxed">\s*<tr><th>(.+?)</th><th>(.+?)</th></tr>'
         r'((.|\n)+?)</table>',
         r'\n.TS\nallbox tab(|);\nc c\nl lx .\n\1|\2\n\3\n.TE\n.sp\n', 0),
        (r'<tr><td>(.+?)</td><td>(.+?)</td></tr>',
         r'\1|T{\n\2\nT}\n', re.DOTALL),
        # Single-column table
        (r'<table class="boxed"><tr><th>(.+?)</th></tr>(.+?)</table>',
         r'\n.TS\nallbox;\nc\nl .\n\1\n\2\n.TE\n.sp\n', 0),
        (r'<tr><td>(.+?)</td></tr>', r'\nT{\1\nT}\n.sp\n', 0),
        # Remove snippet line numbers
        (r'<td class="rownum">.+</td>', r'', 0),
        
        # Footer
        (r'<div id="footer">.*?</div>',
         r'\n.SE\n.SH REFERENCE\n'
         r'cplusplus.com, 2000-2010 - All rights reserved.',
         re.DOTALL),
        # 'br' tag
        (r'<br>', r'\n.br\n', 0),
        # 'dd' 'dt' tag
        (r'<dt>(.+?)</dt>\s*<dd>(.+?)</dd>', r'.IP "\1"\n\2\n', re.DOTALL),
        # Bold
        (r'<strong>(.+?)</strong>', r'\n.B \1\n', 0),
        # -
        (r'-', r'\-', 0),
        # Any other tags
        (r'<script[^>]*>[^<]*</script>', r'', 0),
        (r'<.*?>', r'', re.DOTALL),
        # Misc
        (r'&lt;', r'<', 0), 
        (r'&gt;', r'>', 0),
        (r'&amp;', r'&', 0),
        (r'&nbsp;', r' ', 0),
        (u'\x0d', r'\n.br\n', 0),
        (r'>/">', r'', 0),
        (r'/">', r'', 0),
        # Remove empty lines
        (r'\n\s*\n+', r'\n', 0),
        (r'\n\n+', r'\n', 0),
        # Remove dumplicate .br
        (r'\n.br\n.br\n', r'\n.br\n', 0)
      ]

def cplusplus2groff(data):
    '''
    Convert HTML text from cplusplus.com to Groff-formated text.
    '''
    # Remove sidebar
    try:
        data = data[data.index('<div class="doctop"><h1>'):]
    except ValueError: pass

    # Preprocess 'code' tag
    code_sections = re.findall(r'<code>.+?</code>', data, re.DOTALL)
    for st in code_sections:
        sts = re.sub(r'\n', r'\n.br\n', st)
        data = data.replace(st, sts)

    # Replace all
    for rp in rps:
        data = re.compile(rp[0], rp[2]).sub(rp[1], data)

    # Upper case all section headers
    for st in re.findall(r'.SH .*\n', data):
        data = data.replace(st, st.upper())

    # Add tags to member functions
    # e.g. insert -> vector::insert
    #
    # .SE is a pseudo macro I created which means 'SECTION END'
    # The reason I use it is because I need a marker to know where section ends.
    # re.findall find patterns which do not overlap, which means if I do this:
    # secs = re.findall(r'\n\.SH "(.+?)"(.+?)\.SH', data, re.DOTALL)
    # re.findall will skip the later .SH tag and thus skip the later section.
    # To fix this, '.SE' is used to mark the end of the section so the next
    # '.SH' can be find by re.findall

    page_type =  re.search(r'\n\.SH TYPE\n(.+?)\n', data)
    if page_type and 'class' in page_type.group(1):
        # Member functions
        class_name = re.search(r'\n\.SH NAME\n(.+?) ', data).group(1)

        secs = re.findall(r'\n\.SH "(.+?)"(.+?)\.SE', data, re.DOTALL)

        for sec, content in secs:
            if 'MEMBER' in sec and 'INHERITED' not in sec and\
               sec != 'MEMBER TYPES':
                contents = re.sub(r'\n\.IP "([^:]+?)"', r'\n\.IP "%s::\1"'
                                  % class_name, content)
                # Replace (constructor) (destructor)
                contents = re.sub(r'\(constructor\)', r'%s' % class_name,
                                  contents)
                contents = re.sub(r'\(destructor\)', r'~%s' % class_name,
                                  contents)
                data = data.replace(content, contents)
            elif 'MEMBER' in sec and 'INHERITED' in sec:
                inherit = re.search(r'.+?INHERITED FROM (.+)',
                                    sec).group(1).lower()
                contents = re.sub(r'\n\.IP "(.+)"', r'\n\.IP "%s::\1"'
                                  % inherit, content)
                data = data.replace(content, contents)

    # Remove invalid marking in tables
    for st in re.findall(r'\.TS(.+?)\.TE', data, re.DOTALL):
        sts = re.sub(r'\n\...\n', r'\n', st)
        sts = re.sub(r'\n\.B (.+?)\n', r'\1', sts)
        sts = re.sub(r'\n\.', r'\n\\.', sts)
        index = data.index(st)
        data = data[:index] + sts + data[index + len(st):]

    # Remove pseudo macro .SE
    data = data.replace('\n.SE', '')

    return data

def groff2man(data):
    '''
    Read groff-formated text and output man pages.
    '''
    width = get_width()

    cmd = 'groff -t -Tascii -m man -rLL=%dn -rLT=%dn' % (width, width)
    handle = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE,
                                               stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE)
    man_text, stderr = handle.communicate(data)
    return man_text

def cplusplus2man(data):
    '''
    Convert HTML text from cplusplus.com to man pages.
    '''
    groff_text = cplusplus2groff(data)
    man_text = groff2man(groff_text)
    return man_text

def get_width():
    '''
    Calculate appropriate width for groff
    '''
    # Get terminal size
    ws = struct.pack("HHHH", 0, 0, 0, 0)
    ws = fcntl.ioctl(0, termios.TIOCGWINSZ, ws)
    lines, columns, x, y = struct.unpack("HHHH", ws)
    width = columns * 39 / 40
    if width >= columns -2: width = columns -2
    return width

def test():
    '''
    Simple Text
    '''
    #name = raw_input('What manual page do you want?')
    name = 'streambuf'
    ifs = urllib.urlopen('http://www.cplusplus.com/' + name)
    print cplusplus2groff(ifs.read()),

if __name__ == '__main__':
    test()
