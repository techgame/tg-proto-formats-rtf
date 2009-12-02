#!/usr/bin/env python
##~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~##
##~ Copyright (C) 2002-2009  TechGame Networks, LLC.              ##
##~                                                               ##
##~ This library is free software; you can redistribute it        ##
##~ and/or modify it under the terms of the BSD style License as  ##
##~ found in the LICENSE file included with this distribution.    ##
##~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~##

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Imports 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import os, sys
import re
from functools import partial

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Definitions 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def reFlatten(matcher, useGroups=True):
    if isinstance(matcher, basestring):
        return matcher

    parts = []
    for e in matcher:
        if isinstance(e, tuple):
            e = (e[0], reFlatten(e[1], useGroups))
            if useGroups:
                parts.append('(?P<%s>%s)' % e)
                continue
            else:
                e = e[1]

        parts.append(e)
    return ''.join(parts)
 
class RTFScanner(re.Scanner, object):
    structure = [
        ('open', r'\{'),
        ('close', r'\}'),
        ('command', [r'\\', 
                ('cmd', r'[A-Za-z]+'), # command name
                ('param', r'-?[0-9]+'), '?', # parameter
                '(?:[ ]|(?=[^A-Za-z])|$)', # delimiter, as defined by RTF spec
                ]),
        ('uchar', [r"\\'", ('value', r"[0-9A-Fa-f]{2}")]),
        ('symbol', [r'\\', # symbol is anything that doesn't match a command char
                ('sym', r"[^A-Za-z']")]),
        ('body', # everything except escape, group open/close, or newlines
                r'[^\\{}\n\r]*'),
        ]

    def __init__(self):
        self.lst = self.compile()
        re.Scanner.__init__(self, self.lst)

    def compile(self):
        lst = []
        for name, expr in self.structure:
            if name:
                fn = getattr(self, '_on_'+name)
            else: fn = None

            expr = reFlatten(expr, True)
            fn = partial(fn, expr=re.compile(expr))
            lst.append((expr, fn))
        return lst

    def __call__(self, line):
        return self.scan(line)

    def _on_open(self, scanner, item, expr):
        return ('open',)
    def _on_close(self, scanner, item, expr):
        return ('close',)
    def _on_command(self, scanner, item, expr):
        args = expr.match(item+'\0').groups()
        return ('command',)+ args
    def _on_symbol(self, scanner, item, expr):
        sym = expr.match(item).group(1)
        return ('symbol', sym)
    def _on_body(self, scanner, item, expr):
        assert '}' not in item
        assert '{' not in item
        return ('body', item)
    def _on_uchar(self, scanner, item, expr):
        c = expr.match(item).group(1)
        c = unichr(int(c, 16))
        return ('body', c)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class  RTFParser(object):
    RTFScanner = RTFScanner
    _scanner = None
    def getScanner(self):
        r = self._scanner
        if r is None:
            r = self.RTFScanner()
            self._scanner = r
        return r
    scanner = property(getScanner)

    def feed(self, line):
        r = []
        for item in self.scanner(line):
            if not item: continue
            if isinstance(item, list):
                r.extend(item)
            else: 
                assert '}' not in item
                assert '{' not in item
                r.append(('raw', item))
        return r

class RTFDocBuilder(object):
    RTFParser = RTFParser
    root = result = last = None

    def __init__(self):
        self.stack = []
        self.parser = self.RTFParser()

    def read(self, file):
        for line in file:
            self.feed

    _dispMap = None
    def _getDispatchMap(self):
        dispMap = self._dispMap
        if dispMap is None:
            dispMap = dict((k,getattr(self, k)) 
                for k in ['open', 'close', 'command', 'symbol', 'body', 'raw'])
            self._dispMap = dispMap
        return dispMap

    def feed(self, line):
        dispMap = self._getDispatchMap()
        for e in self.parser.feed(line):
            fn = dispMap[e[0]]
            fn(*e[1:])

    newGroup = list
    def open(self):
        group = self.newGroup()
        stack = self.stack
        if stack:
            stack[-1].append(group)
        elif self.root is None: 
            self.root = group
        else:
            raise RuntimeError("Document already closed")
        stack.append(group)
    def close(self):
        stack = self.stack
        group = stack.pop()
        self.last = group
        if not stack:
            self.result = group
        return group
    def command(self, cmd, arg=None):
        self.addOp(cmd, arg)
    def symbol(self, sym):
        if sym not in '\n\r':
            self.addOp(True, sym)
        else: self.addText(sym)
    def body(self, body):
        self.addText(body)
    def raw(self, item):
        if self.stack:
            self.addOp(False, item)

    def addOp(self, op, *args):
        e = (op,)+args
        self.stack[-1].append(e)
        return e
    def addText(self, text):
        top = self.stack[-1]
        if isinstance(top[-1], basestring):
            top[-1] += text
        else: top.append(text)

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Main 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

if __name__=='__main__':
    from pprint import pprint
    for fn in sys.argv[1:]:
        builder = RTFDocBuilder()
        for line in open(fn, "rb"):
            builder.feed(line)

        if builder.result:
            pprint(builder.result)
        else:
            pprint(builder.root)

