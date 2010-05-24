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
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
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
        return ('openGroup',)
    def _on_close(self, scanner, item, expr):
        return ('closeGroup',)
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

class RTFParser(object):
    RTFScanner = RTFScanner
    _scanner = None
    def getScanner(self):
        r = self._scanner
        if r is None:
            r = self.RTFScanner()
            self._scanner = r
        return r
    scanner = property(getScanner)

    def feed(self, data):
        r = []
        for line in StringIO(data):
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
        self.parser = self.RTFParser()
        self.stack = []
        self.openGroup()

    def read(self, aFile):
        if isinstance(aFile, basestring):
            raise ValueError("Read requires a file like object, not a string")
        for line in aFile:
            self.feed(line)
    def readData(self, aBuffer):
        return self.read(StringIO(aBuffer))

    _dispMap = None
    def _getDispatchMap(self):
        dispMap = self._dispMap
        if dispMap is None:
            dispMap = dict((k,getattr(self, k)) 
                for k in ['openGroup', 'closeGroup', 'command', 'symbol', 'body', 'raw'])
            self._dispMap = dispMap
        return dispMap

    def feed(self, aBuffer):
        dispMap = self._getDispatchMap()
        for e in self.parser.feed(aBuffer):
            fn = dispMap[e[0]]
            fn(*e[1:])

    def close(self):
        r = self.last
        while self.stack:
            r = self.closeGroup()

        r = self.asResultGroup(r)
        self.result = r
        return r

    def asResultGroup(self, group):
        return self.foldSimpleGroups(group)
    def foldSimpleGroups(self, group):
        while len(group) == 1 and isinstance(group[0], type(group)):
            group = group[0]
        return group

    newGroup = list
    def addNewGroup(self, top):
        group = self.newGroup()
        top.append(group)
        return group
    def newRootGroup(self):
        group = self.newGroup()
        self.root = group
        return group
    def openGroup(self):
        stack = self.stack
        if stack:
            group = self.addNewGroup(stack[-1])
        elif self.root is None:
            group = self.newRootGroup()
        else: 
            raise RuntimeError("Document already closed")

        if group is not None:
            stack.append(group)
            return group
    def closeGroup(self):
        stack = self.stack
        group = stack.pop()
        self.last = group
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
        if top and isinstance(top[-1], basestring):
            top[-1] += text
        else: top.append(text)

class RTFPlaintextBuilder(RTFDocBuilder):
    def raw(self, item):
        top = self.stack[-1]
        if top and isinstance(top[-1], basestring):
            top[-1] += item
        else: top.append(item)
    def asResultGroup(self, group):
        group = self.foldSimpleGroups(group)
        group[:] = (e for e in group if isinstance(e, basestring))
        return group

    @classmethod
    def rtfAsText(klass, rtfText):
        builder = klass()
        builder.readData(rtfText)
        return ''.join(builder.close())

#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#~ Main 
#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

if __name__=='__main__':
    from pprint import pprint
    for fn in sys.argv[1:]:
        #builder = RTFDocBuilder()
        builder = RTFPlaintextBuilder()
        for line in open(fn, "rb"):
            builder.feed(line)
        r = builder.close()

        print
        print "FILE:", fn
        print ''.join(r)
        #pprint(r)

