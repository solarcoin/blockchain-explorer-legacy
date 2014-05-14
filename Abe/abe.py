# url !/usr/bin/env python
# Copyright(C) 2011,2012,2013 by Abe developers.

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see
# <http://www.gnu.org/licenses/agpl.html>.

import sys
import os
import optparse
import re
from cgi import escape
import posixpath
import wsgiref.util
import time
import calendar
import math
import logging
import json

import version
import DataStore
import readconf
#from urllib2 import Request, urlopen
import requests

# bitcointools -- modified deserialize.py to return raw transaction
import deserialize
import util  # Added functions.
import base58

import view_templates

__version__ = version.__version__

ABE_APPNAME = "Abe"
ABE_VERSION = __version__
ABE_URL = 'https://github.com/bitcoin-abe/bitcoin-abe'

COPYRIGHT_YEARS = '2011'
COPYRIGHT = "Abe developers"
COPYRIGHT_URL = 'https://github.com/bitcoin-abe'

DONATIONS_BTC = '1PWC7PNHL1SgvZaN7xEtygenKjWobWsCuf'
DONATIONS_NMC = 'NJ3MSELK1cWnqUa6xhF2wUYAnz3RSrWXcK'

TIME1970 = time.strptime('1970-01-01','%Y-%m-%d')
EPOCH1970 = calendar.timegm(TIME1970)

# Abe-generated content should all be valid HTML and XHTML fragments.
# Configurable templates may contain either.  HTML seems better supported
# under Internet Explorer.
DEFAULT_CONTENT_TYPE = "text/html; charset=utf-8"
DEFAULT_HOMEPAGE = "home";
DEFAULT_HOMEPAGE_TEMPLATE = view_templates.get_default_homepage_template()
DEFAULT_LOG_FORMAT = "%(message)s"

# XXX This should probably be a property of chain, or even a query param.
LOG10COIN = 8
COIN = 10 ** LOG10COIN

# It is fun to change "6" to "3" and search lots of addresses.
ADDR_PREFIX_RE = re.compile('[1-9A-HJ-NP-Za-km-z]{6,}\\Z')
HEIGHT_RE = re.compile('(?:0|[1-9][0-9]*)\\Z')
HASH_PREFIX_RE = re.compile('[0-9a-fA-F]{0,64}\\Z')
HASH_PREFIX_MIN = 6

NETHASH_HEADER = """\
blockNumber:          height of last block in interval + 1
time:                 block time in seconds since 0h00 1 Jan 1970 UTC
target:               decimal target at blockNumber
avgTargetSinceLast:   harmonic mean of target over interval
difficulty:           difficulty at blockNumber
hashesToWin:          expected number of hashes needed to solve a block at this difficulty
avgIntervalSinceLast: interval seconds divided by blocks
netHashPerSecond:     estimated network hash rate over interval

Statistical values are approximate and differ slightly from http://blockexplorer.com/q/nethash.

/chain/CHAIN/q/nethash[/INTERVAL[/START[/STOP]]]
Default INTERVAL=144, START=0, STOP=infinity.
Negative values back from the last block.
Append ?format=json to URL for headerless, JSON output.

blockNumber,time,target,avgTargetSinceLast,difficulty,hashesToWin,avgIntervalSinceLast,netHashPerSecond
START DATA
"""

NETHASH_SVG_TEMPLATE = view_templates.get_nethash_svg_template()

# How many addresses to accept in /unspent/ADDR|ADDR|...
MAX_UNSPENT_ADDRESSES = 200


def make_store(args):
    store = DataStore.new(args)
    if (not args.no_load):
        store.catch_up()
    return store

class NoSuchChainError(Exception):
    """Thrown when a chain lookup fails"""

class PageNotFound(Exception):
    """Thrown when code wants to return 404 Not Found"""

class Redirect(Exception):
    """Thrown when code wants to redirect the request"""

class Streamed(Exception):
    """Thrown when code has written the document to the callable
    returned by start_response."""

class Abe:
    def __init__(abe, store, args):
        abe.store = store
        abe.args = args
        abe.htdocs = args.document_root or find_htdocs()
        abe.static_path = '' if args.static_path is None else args.static_path
        abe.template_vars = args.template_vars.copy()
        abe.template_vars['STATIC_PATH'] = (
            abe.template_vars.get('STATIC_PATH', abe.static_path))
        abe.template = flatten(args.template)
        abe.debug = args.debug
        abe.log = logging.getLogger(__name__)
        abe.log.info('Abe initialized.')
        abe.home = str(abe.template_vars.get("HOMEPAGE", DEFAULT_HOMEPAGE))
        if not args.auto_agpl:
            abe.template_vars['download'] = (
                abe.template_vars.get('download', ''))
        abe.base_url = args.base_url
        abe.address_history_rows_max = int(
            args.address_history_rows_max or 1000)

        if args.shortlink_type is None:
            abe.shortlink_type = ("firstbits" if store.use_firstbits else
                                  "non-firstbits")
        else:
            abe.shortlink_type = args.shortlink_type
            if abe.shortlink_type != "firstbits":
                abe.shortlink_type = int(abe.shortlink_type)
                if abe.shortlink_type < 2:
                    raise ValueError("shortlink-type: 2 character minimum")
            elif not store.use_firstbits:
                abe.shortlink_type = "non-firstbits"
                abe.log.warn("Ignoring shortlink-type=firstbits since" +
                             " the database does not support it.")
        if abe.shortlink_type == "non-firstbits":
            abe.shortlink_type = 10

    def __call__(abe, env, start_response):
        import urlparse
        print "CALL"

        status = '200 OK'
        page = {
            "title": [escape(ABE_APPNAME), " ", ABE_VERSION],
            "body": [],
            "env": env,
            "params": {},
            "dotdot": "../" * (env['PATH_INFO'].count('/') - 1),
            "start_response": start_response,
            "content_type": str(abe.template_vars['CONTENT_TYPE']),
            "template": abe.template,
            "chain": None,
            }
        if 'QUERY_STRING' in env:
            page['params'] = urlparse.parse_qs(env['QUERY_STRING'])

        if abe.fix_path_info(env):
            abe.log.debug("fixed path_info")
            return redirect(page)

        cmd = wsgiref.util.shift_path_info(env)
        print "CMD: %s" % cmd
        handler = abe.get_handler(cmd)
        print "Handler: %r" % handler

        try:
            if handler is None:
                return abe.serve_static(cmd + env['PATH_INFO'], start_response)

            if (not abe.args.no_load):
                # Always be up-to-date, even if we means having to wait
                # for a response!  XXX Could use threads, timers, or a
                # cron job.
                abe.store.catch_up()

            tvars = abe.template_vars.copy()
            tvars['dotdot'] = page['dotdot']
            page['template_vars'] = tvars

            handler(page)
        except PageNotFound:
            status = '404 Not Found'
            page["body"] = ['<p class="error">Sorry, ', env['SCRIPT_NAME'],
                            env['PATH_INFO'],
                            ' does not exist on this server.</p>']
        except NoSuchChainError, e:
            page['body'] += [
                '<p class="error">'
                'Sorry, I don\'t know about that chain!</p>\n']
        except Redirect:
            return redirect(page)
        except Streamed:
            return ''
        except:
            abe.store.rollback()
            raise

        abe.store.rollback()  # Close imlicitly opened transaction.

        start_response(status, [('Content-type', page['content_type']),
                                ('Cache-Control', 'max-age=30')])

        tvars['title'] = flatten(page['title'])
        tvars['h1'] = flatten(page.get('h1') or page['title'])
        tvars['body'] = flatten(page['body'])
        if abe.args.auto_agpl:
            tvars['download'] = (
                ' <a href="' + page['dotdot'] + 'download">Source</a>')

        content = page['template'] % tvars
        if isinstance(content, unicode):
            content = content.encode('UTF-8')
        return content

    def get_handler(abe, cmd):
        return getattr(abe, 'handle_' + cmd, None)

    def handle_home(abe, page):
        body = page['body']
        show_search_form = True
        
        now = time.time() - EPOCH1970

        rows = abe.store.selectall("""
            SELECT c.chain_name, b.block_height, b.block_nTime, b.block_hash,
                   b.block_total_seconds, b.block_total_satoshis,
                   b.block_satoshi_seconds,
                   b.block_total_ss, c.chain_id, c.chain_code3,
                   c.chain_address_version, c.chain_last_block_id
              FROM chain c
              JOIN block b ON (c.chain_last_block_id = b.block_id)
             ORDER BY c.chain_name
        """)
        
        for row in rows:
            name = row[0]
            chain = abe._row_to_chain((row[8], name, row[9], row[10], row[11]))
            chain_id = row[8]
 
            if row[1] is not None:
                
                #lots of this data isn't being used - should be cleaned up but it's only one row per page load
                (height, nTime, hash) = (
                    int(row[1]), int(row[2]), abe.store.hashout_hex(row[3]))

                if row[6] is not None and row[7] is not None:
                    (seconds, satoshis, ss, total_ss) = (
                        int(row[4]), int(row[5]), int(row[6]), int(row[7]))

                    started = nTime - seconds
                    chain_age = now - started
                    since_block = now - nTime
                    totalcold = 0
                cold_storage_wallets = abe.get_cold_storage()
                
                #format cold storage wallets for display
                for wallet in cold_storage_wallets:
                    cold_storage_wallets[wallet] = format_satoshis(cold_storage_wallets[wallet], chain)
                
                body += view_templates.generate_homepage(height, format_satoshis(satoshis, chain), cold_storage_wallets, show_search_form)

        

	if len(rows) == 0:
            body += ['<p>No block data found.</p>\n']

    def _chain_fields(abe):
        return ["id", "name", "code3", "address_version", "last_block_id"]

    def _row_to_chain(abe, row):
        if row is None:
            raise NoSuchChainError()
        chain = {}
        fields = abe._chain_fields()
        for i in range(len(fields)):
            chain[fields[i]] = row[i]
        chain['address_version'] = abe.store.binout(chain['address_version'])
        return chain

    def chain_lookup_by_name(abe, symbol):
        if symbol is None:
            return abe.get_default_chain()
        return abe._row_to_chain(abe.store.selectrow("""
            SELECT chain_""" + ", chain_".join(abe._chain_fields()) + """
              FROM chain
             WHERE chain_name = ?""", (symbol,)))

    def get_default_chain(abe):
        return abe.chain_lookup_by_name('Bitcoin')

    def chain_lookup_by_id(abe, chain_id):
        return abe._row_to_chain(abe.store.selectrow("""
            SELECT chain_""" + ", chain_".join(abe._chain_fields()) + """
              FROM chain
             WHERE chain_id = ?""", (chain_id,)))

    def call_handler(abe, page, cmd):
        handler = abe.get_handler(cmd)
        if handler is None:
            raise PageNotFound()
        handler(page)

    def handle_browse_blocks(abe, page):
        symbol = wsgiref.util.shift_path_info(page['env'])
        chain = abe.chain_lookup_by_name(symbol)
        page['chain'] = chain

        cmd = wsgiref.util.shift_path_info(page['env'])
        
        if cmd == '':
            page['env']['SCRIPT_NAME'] = page['env']['SCRIPT_NAME'][:-1]
            raise Redirect()
        if cmd == 'chain' or cmd == 'chains':
            raise PageNotFound()
        if cmd is not None:
            abe.call_handler(page, cmd)
            return

        page['title'] = chain['name'] + 'All Blocks'

        body = page['body']
        show_search_form = True

        count = get_int_param(page, 'count') or 20
        hi = get_int_param(page, 'hi')
        orig_hi = hi

        if hi is None:
            row = abe.store.selectrow("""
                SELECT b.block_height
                  FROM block b
                  JOIN chain c ON (c.chain_last_block_id = b.block_id)
                 WHERE c.chain_id = ?
            """, (chain['id'],))
            if row:
                hi = row[0]
        
        #FIX: this should be a view
        if hi is None:
            if orig_hi is None and count > 0:
                body += ['<p>I have no blocks in this chain.</p>']
            else:
                body += ['<p class="error">'
                         'The requested range contains no blocks.</p>\n']
            return

        rows = abe.store.selectall("""
            SELECT b.block_hash, b.block_height, b.block_nTime, b.block_num_tx,
                   b.block_nBits, b.block_value_out,
                   b.block_total_seconds, b.block_satoshi_seconds,
                   b.block_total_satoshis, b.block_ss_destroyed,
                   b.block_total_ss
              FROM block b
              JOIN chain_candidate cc ON (b.block_id = cc.block_id)
             WHERE cc.chain_id = ?
               AND cc.block_height BETWEEN ? AND ?
               AND cc.in_longest = 1
             ORDER BY cc.block_height DESC LIMIT ?
        """, (chain['id'], hi - count + 1, hi, count))
        
        

        if hi is None:
            hi = int(rows[0][1])
        #basename = os.path.basename(page['env']['PATH_INFO'])
        basename = page['env']['SCRIPT_NAME']
        block_pager = view_templates.generate_block_pager(basename, hi, count)

        block_dict = {}
        
        
        for row in rows:
            (hash, height, nTime, num_tx, nBits, value_out,
             seconds, ss, satoshis, destroyed, total_ss) = row
            nTime = int(nTime)
            value_out = int(value_out)
            seconds = int(seconds)
            satoshis = int(satoshis)
            ss = int(ss)
            total_ss = int(total_ss)
            
            block_num = 'block_%s' % str(height)
            
            block_dict[block_num] = {}
            block_dict[block_num]['link'] = '<a href="%sblock/%s">%s</a>' % \
            (page['dotdot'], abe.store.hashout_hex(hash), str(height))
            
            block_dict[block_num]['time'] = format_time(int(nTime))
            block_dict[block_num]['num_tx'] = num_tx
            block_dict[block_num]['value'] = format_satoshis(value_out, chain)

        body += view_templates.generate_browse_blocks_page(block_dict, block_pager)

    def _show_block(abe, where, bind, page, dotdotblock, chain):
        address_version = ('\0' if chain is None
                           else chain['address_version'])
        body = page['body']
        sql = """
            SELECT
                block_id,
                block_hash,
                block_version,
                block_hashMerkleRoot,
                block_nTime,
                block_nBits,
                block_nNonce,
                block_height,
                prev_block_hash,
                block_chain_work,
                block_value_in,
                block_value_out,
                block_total_satoshis,
                block_total_seconds,
                block_satoshi_seconds,
                block_total_ss,
                block_ss_destroyed,
                block_num_tx
              FROM chain_summary
             WHERE """ + where
        row = abe.store.selectrow(sql, bind)
        if (row is None):
            body += ['<p class="error">Block not found.</p>']
            return
        (block_id, block_hash, block_version, hashMerkleRoot,
         nTime, nBits, nNonce, height,
         prev_block_hash, block_chain_work, value_in, value_out,
         satoshis, seconds, ss, total_ss, destroyed, num_tx) = (
            row[0], abe.store.hashout_hex(row[1]), row[2],
            abe.store.hashout_hex(row[3]), row[4], int(row[5]), row[6],
            row[7], abe.store.hashout_hex(row[8]),
            abe.store.binout_int(row[9]), int(row[10]), int(row[11]),
            None if row[12] is None else int(row[12]),
            None if row[13] is None else int(row[13]),
            None if row[14] is None else int(row[14]),
            None if row[15] is None else int(row[15]),
            None if row[16] is None else int(row[16]),
            int(row[17]),
            )

        next_list = abe.store.selectall("""
            SELECT DISTINCT n.block_hash, cc.in_longest
              FROM block_next bn
              JOIN block n ON (bn.next_block_id = n.block_id)
              JOIN chain_candidate cc ON (n.block_id = cc.block_id)
             WHERE bn.block_id = ?
             ORDER BY cc.in_longest DESC""",
                                  (block_id,))

        display_next_list = []
        
        for row in next_list:
            hash = abe.store.hashout_hex(row[0])
            display_next_list.append(hash)
        
        block_details = {}
        block_details['chain_name'] = escape(chain['name'])
        block_details['block_number'] = height
        block_details['short_link'] = abe.short_link(page, 'b/' + block_shortlink(block_hash))
        block_details['version'] = block_version
        block_details['merkle_root'] = hashMerkleRoot
        block_details['time'] = format_time(nTime)
        block_details['difficulty'] = format_difficulty(util.calculate_difficulty(nBits))
        block_details['nBits'] = nBits
     
        if block_chain_work is not None:
            block_details['cumulative_difficulty'] = format_difficulty(
                    util.work_to_difficulty(block_chain_work))
        else:
            block_details['cumulative_difficulty'] = ''
        block_details['nonce'] = nNonce
        block_details['num_transactions'] = num_tx
        block_details['value_out'] = format_satoshis(value_out, chain)
        block_details['prev_block_hash'] = prev_block_hash
        block_details['parent_address_prefix'] = dotdotblock
        
        if satoshis and (ss is not None):
            block_details['average_coin_age'] = (ss / 86400.0 / satoshis)
        else:
            block_details['average_coin_age'] = ''
        
        
        if total_ss:
            block_details['cumulative_coin_dd'] = (100 * (1 - float(ss) / total_ss))
        else:
            block_details['cumulative_coin_dd'] = ''
            
        tx_ids = []
        txs = {}
        block_out = 0
        block_in = 0
        for row in abe.store.selectall("""
            SELECT tx_id, tx_hash, tx_size, txout_value, pubkey_hash, tx_comment
              FROM txout_detail
             WHERE block_id = ?
             ORDER BY tx_pos, txout_pos
        """, (block_id,)):
            tx_id, tx_hash_hex, tx_size, txout_value, pubkey_hash, tx_comment= (
                row[0], abe.store.hashout_hex(row[1]), int(row[2]),
                int(row[3]), abe.store.binout(row[4]), str(row[5]))
            tx = txs.get(tx_id)
            if tx is None:
                tx_ids.append(tx_id)
                txs[tx_id] = {
                    "hash": tx_hash_hex,
                    "total_out": 0,
                    "total_in": 0,
                    "out": [],
                    "in": [],
                    "size": tx_size,
		            "txComment": tx_comment,
                    }
                tx = txs[tx_id]
            tx['total_out'] += txout_value
            block_out += txout_value
            tx['out'].append({
                    "value": txout_value,
                    "pubkey_hash": pubkey_hash,
                    })
        for row in abe.store.selectall("""
            SELECT tx_id, txin_value, pubkey_hash
              FROM txin_detail
             WHERE block_id = ?
             ORDER BY tx_pos, txin_pos
        """, (block_id,)):
            tx_id, txin_value, pubkey_hash = (
                row[0], 0 if row[1] is None else int(row[1]),
                abe.store.binout(row[2]))
            tx = txs.get(tx_id)
            if tx is None:
                # Strange, inputs but no outputs?
                tx_ids.append(tx_id)
                #row2 = abe.store.selectrow("""
                #    SELECT tx_hash, tx_size FROM tx WHERE tx_id = ?""",
                #                           (tx_id,))
                txs[tx_id] = {
                    "hash": "AssertionFailedTxInputNoOutput",
                    "total_out": 0,
                    "total_in": 0,
                    "out": [],
                    "in": [],
                    "size": -1,
                    }
                tx = txs[tx_id]
            tx['total_in'] += txin_value
            block_in += txin_value
            tx['in'].append({
                    "value": txin_value,
                    "pubkey_hash": pubkey_hash,
                    })

        for tx_id in tx_ids:
            tx = txs[tx_id]
            tx['display_in_transactions'] = []
            tx['display_out_transactions'] = []
           
            #'from' transactions
            is_coinbase = (tx_id == tx_ids[0])
           
            #no 'from' if it's a generated block
            if is_coinbase:
               gen = block_out - block_in
               fees = tx['total_out'] - gen
               tx['display_in_transactions'].append(
                   {'Newly generated block' : "%s new SLR + %s in fees" % (
                        format_satoshis(gen, chain), 
                        format_satoshis(fees, chain))})
            else:
                fees = tx['total_in'] - tx['total_out']
                for txin in tx['in']:
                  #ugly hack to not break hash_to_address
                  display_address = ""
                  display_address = display_address.join(hash_to_address_link(
                    address_version, txin['pubkey_hash'], page['dotdot']))
                  tx['display_in_transactions'].append(
                      {display_address : format_satoshis(txin['value'], \
                      chain)})
            
            #'to' transactions'
            for txout in tx['out']:
                #ugly hack to not break hash_to_address
                display_address = ""
                display_address = display_address.join(hash_to_address_link(
                    address_version, txout['pubkey_hash'], page['dotdot']))
                tx['display_out_transactions'].append(
                      {display_address : format_satoshis(txout['value'], \
                      chain)})
        
        body += view_templates.generate_block_detail_page(
            block_details, display_next_list, tx_ids, txs)

    def handle_block(abe, page):
        abe.log.warn("HANDLE BLOCK")
        block_hash = wsgiref.util.shift_path_info(page['env'])
        if block_hash in (None, '') or page['env']['PATH_INFO'] != '':
            raise PageNotFound()

        block_hash = block_hash.lower()  # Case-insensitive, BBE compatible
        page['title'] = 'Block'

        if not is_hash_prefix(block_hash):
            page['body'] += ['<p class="error">Not a valid block hash.</p>']
            return

        # Try to show it as a block number, not a block hash.

        dbhash = abe.store.hashin_hex(block_hash)

        # XXX arbitrary choice: minimum chain_id.  Should support
        # /chain/CHAIN/block/HASH URLs and try to keep "next block"
        # links on the chain.
        row = abe.store.selectrow("""
            SELECT MIN(cc.chain_id), cc.block_id, cc.block_height
              FROM chain_candidate cc
              JOIN block b ON (cc.block_id = b.block_id)
             WHERE b.block_hash = ? AND cc.in_longest = 1
             GROUP BY cc.block_id, cc.block_height""",
            (dbhash,))
        if row is None:
            abe._show_block('block_hash = ?', (dbhash,), page, '', None)
        else:
            chain_id, block_id, height = row
            chain = abe.chain_lookup_by_id(chain_id)
            page['title'] = [escape(chain['name']), ' ', height]
            abe._show_block('block_id = ?', (block_id,), page, '', chain)

    def handle_tx(abe, page):
        tx_hash = wsgiref.util.shift_path_info(page['env'])
        if tx_hash in (None, '') or page['env']['PATH_INFO'] != '':
            raise PageNotFound()

        tx_hash = tx_hash.lower()  # Case-insensitive, BBE compatible
        page['title'] = ['Transaction ', tx_hash[:10], '...', tx_hash[-4:]]
        body = page['body']

        if not is_hash_prefix(tx_hash):
            body += ['<p class="error">Not a valid transaction hash.</p>']
            return

        row = abe.store.selectrow("""
            SELECT tx_id, tx_version, tx_lockTime, tx_size, tx_comment
              FROM tx
             WHERE tx_hash = ?
        """, (abe.store.hashin_hex(tx_hash),))
        if row is None:
            body += ['<p class="error">Transaction not found.</p>']
            return
        tx_id, tx_version, tx_lockTime, tx_size = (
            int(row[0]), int(row[1]), int(row[2]), int(row[3]))
        tx_comment = str(row[4])

        block_rows = abe.store.selectall("""
            SELECT c.chain_name, cc.in_longest,
                   b.block_nTime, b.block_height, b.block_hash,
                   block_tx.tx_pos
              FROM chain c
              JOIN chain_candidate cc ON (cc.chain_id = c.chain_id)
              JOIN block b ON (b.block_id = cc.block_id)
              JOIN block_tx ON (block_tx.block_id = b.block_id)
             WHERE block_tx.tx_id = ?
             ORDER BY c.chain_id, cc.in_longest DESC, b.block_hash
        """, (tx_id,))

        def parse_row(row):
            pos, script, value, o_hash, o_pos, binaddr = row
            return {
                "pos": int(pos),
                "script": abe.store.binout(script),
                "value": None if value is None else int(value),
                "o_hash": abe.store.hashout_hex(o_hash),
                "o_pos": None if o_pos is None else int(o_pos),
                "binaddr": abe.store.binout(binaddr),
                }

        def row_to_html(row, this_ch, other_ch, no_link_text):
            body = page['body']
            body += [
                '<tr>\n',
                '<td><a name="', this_ch, row['pos'], '">', row['pos'],
                '</a></td>\n<td>']
            if row['o_hash'] is None:
                body += [no_link_text]
            else:
                body += [
                    '<a href="', row['o_hash'], '#', other_ch, row['o_pos'],
                    '">', row['o_hash'][:10], '...:', row['o_pos'], '</a>']
            body += [
                '</td>\n',
                '<td>', format_satoshis(row['value'], chain), '</td>\n',
                '<td>']
            if row['binaddr'] is None:
                body += ['Unknown']
            else:
                body += hash_to_address_link(chain['address_version'],
                                             row['binaddr'], '../')
            body += ['</td>\n']
            if row['script'] is not None:
                body += ['<td>', escape(decode_script(row['script'])),
                '</td>\n']
            body += ['</tr>\n']

        # XXX Unneeded outer join.
        in_rows = map(parse_row, abe.store.selectall("""
            SELECT
                txin.txin_pos""" + (""",
                txin.txin_scriptSig""" if abe.store.keep_scriptsig else """,
                NULL""") + """,
                txout.txout_value,
                COALESCE(prevtx.tx_hash, u.txout_tx_hash),
                COALESCE(txout.txout_pos, u.txout_pos),
                pubkey.pubkey_hash
              FROM txin
              LEFT JOIN txout ON (txout.txout_id = txin.txout_id)
              LEFT JOIN pubkey ON (pubkey.pubkey_id = txout.pubkey_id)
              LEFT JOIN tx prevtx ON (txout.tx_id = prevtx.tx_id)
              LEFT JOIN unlinked_txin u ON (u.txin_id = txin.txin_id)
             WHERE txin.tx_id = ?
             ORDER BY txin.txin_pos
        """, (tx_id,)))

        # XXX Only two outer JOINs needed.
        out_rows = map(parse_row, abe.store.selectall("""
            SELECT
                txout.txout_pos,
                txout.txout_scriptPubKey,
                txout.txout_value,
                nexttx.tx_hash,
                txin.txin_pos,
                pubkey.pubkey_hash
              FROM txout
              LEFT JOIN txin ON (txin.txout_id = txout.txout_id)
              LEFT JOIN pubkey ON (pubkey.pubkey_id = txout.pubkey_id)
              LEFT JOIN tx nexttx ON (txin.tx_id = nexttx.tx_id)
             WHERE txout.tx_id = ?
             ORDER BY txout.txout_pos
        """, (tx_id,)))
        
        def row_to_dict(row, this_ch, other_ch, no_link_text):
            return_dict = {}
            return_dict['index'] = row['pos']
            return_dict['link_text'] = ""
            if row['o_hash'] is None:
                return_dict['o_hash'] = no_link_text
            if row['o_hash'] is not None:
                return_dict['link_text'] = "%s" % (row['o_hash'] + '#' + other_ch + str(row['o_pos']))
            return_dict['amount'] = format_satoshis(row['value'], chain)
            return_dict['binaddr'] = ""
            if row['binaddr'] is None:
                return_dict['binaddr'] = "Unknown"
            else:
                return_dict['binaddr'] = return_dict['binaddr'].join(
                    hash_to_address_link(chain['address_version'],
                                             row['binaddr'], '../'))
                
            return_dict['script'] = ""
            if row['script'] is not None:
                return_dict['script'] = escape(decode_script(row['script']))
            return return_dict

        # XXX Unneeded outer join.
        in_rows = map(parse_row, abe.store.selectall("""
            SELECT
                txin.txin_pos""" + (""",
                txin.txin_scriptSig""" if abe.store.keep_scriptsig else """,
                NULL""") + """,
                txout.txout_value,
                COALESCE(prevtx.tx_hash, u.txout_tx_hash),
                COALESCE(txout.txout_pos, u.txout_pos),
                pubkey.pubkey_hash
              FROM txin
              LEFT JOIN txout ON (txout.txout_id = txin.txout_id)
              LEFT JOIN pubkey ON (pubkey.pubkey_id = txout.pubkey_id)
              LEFT JOIN tx prevtx ON (txout.tx_id = prevtx.tx_id)
              LEFT JOIN unlinked_txin u ON (u.txin_id = txin.txin_id)
             WHERE txin.tx_id = ?
             ORDER BY txin.txin_pos
        """, (tx_id,)))

        # XXX Only two outer JOINs needed.
        out_rows = map(parse_row, abe.store.selectall("""
            SELECT
                txout.txout_pos,
                txout.txout_scriptPubKey,
                txout.txout_value,
                nexttx.tx_hash,
                txin.txin_pos,
                pubkey.pubkey_hash
              FROM txout
              LEFT JOIN txin ON (txin.txout_id = txout.txout_id)
              LEFT JOIN pubkey ON (pubkey.pubkey_id = txout.pubkey_id)
              LEFT JOIN tx nexttx ON (txin.tx_id = nexttx.tx_id)
             WHERE txout.tx_id = ?
             ORDER BY txout.txout_pos
        """, (tx_id,)))

        def sum_values(rows):
            ret = 0
            for row in rows:
                if row['value'] is None:
                    return None
                ret += row['value']
            return ret

        value_in = sum_values(in_rows)
        value_out = sum_values(out_rows)
        is_coinbase = None

        #shortlink
        display_transaction = {}
        display_transaction['shortlink'] = abe.short_link(
            page, 't/' + hexb58(tx_hash[:14]))
        
        #hash
        display_transaction['hash'] = tx_hash
        
        #in blocks
        display_transaction['in_blocks'] = []
        
        chain = None
        
        #collect all blocks this tx appears in
        for row in block_rows:
            (name, in_longest, nTime, height, blk_hash, tx_pos) = (
                row[0], int(row[1]), int(row[2]),
                None if row[3] is None else int(row[3]),
                abe.store.hashout_hex(row[4]), int(row[5]))
            if chain is None:
                chain = abe.chain_lookup_by_name(name)
                is_coinbase = (tx_pos == 0)
            elif name <> chain['name']:
                abe.log.warn('Transaction ' + tx_hash + ' in multiple chains: '
                             + name + ', ' + chain['name'])
            
            #block hash                 
            display_transaction['in_blocks'].append(
                {blk_hash : format_time(nTime)})
            

        if chain is None:
            abe.log.warn('Assuming default chain for Transaction ' + tx_hash)
            chain = abe.get_default_chain()
        
        display_transaction['num_inputs'] = len(in_rows)
        display_transaction['num_outputs'] = len(out_rows)
        display_transaction['total_value_in'] = format_satoshis(value_in, chain)
        display_transaction['total_value_out'] = format_satoshis(
            value_out, chain)
        display_transaction['size'] = tx_size
        display_transaction['fee'] = format_satoshis(0 if is_coinbase else
                                     (value_in and value_out and
                                      value_in - value_out), chain)
        display_transaction['tx_comment'] = tx_comment
        

        in_row_dict = []
        out_row_dict = []
        
        for row in in_rows:
            in_row_dict.append(row_to_dict(row, 'i', 'o',
                        'Generation' if is_coinbase else 'Unknown'))
        
        for row in out_rows:
            out_row_dict.append(row_to_dict(row, 'o', 'i', 'Not yet redeemed'))
        
        body += view_templates.generate_transaction_detail_page(
            display_transaction, in_row_dict, out_row_dict)

    def handle_rawtx(abe, page):
        abe.do_raw(page, abe.do_rawtx)

    def do_rawtx(abe, page, chain):
        tx_hash = wsgiref.util.shift_path_info(page['env'])
        if tx_hash in (None, '') or page['env']['PATH_INFO'] != '' \
                or not is_hash_prefix(tx_hash):
            return 'ERROR: Not in correct format'  # BBE compatible

        tx = abe.store.export_tx(tx_hash=tx_hash.lower())
        if tx is None:
            return 'ERROR: Transaction does not exist.'  # BBE compatible
        return json.dumps(tx, sort_keys=True, indent=2)

    def handle_messages(abe, page):
        reclimit = wsgiref.util.shift_path_info(page['env'])

#       if reclimit in (None, '','all') or page['env']['PATH_INFO'] != '':
#          reclimit = 1000000000
#	elif reclimit == 'recent':
        reclimit = 150

        page['title'] = 'Transaction Messages'
	body = page['body']

        txrows = abe.store.selectall("""
            SELECT tx.tx_comment, b.block_height, tx.tx_hash, b.block_hash
              FROM tx
	      LEFT JOIN block_tx bt ON (bt.tx_id = tx.tx_id)
	      LEFT JOIN block b ON (b.block_id = bt.block_id)
	      WHERE length(tx.tx_comment) >1
	      ORDER BY b.block_height desc
	      LIMIT ?""",
	      (reclimit,))

	if txrows is None:
	   body += ['<p class="error">No transaction messages found.</p>']
           return
	else:
	   body += [
              '<br /><br /><table><tr><th>Block</th><th>Transaction</th><th>Comment</th></tr>\n']

	   for row in txrows:
	      if row[0] is not None:
		 (txcomment, height, txhash, blockhash) = (
		    str(row[0]), int(row[1]), abe.store.hashout_hex(row[2]), abe.store.hashout_hex(row[3]))

	      body += [
                 '<tr><td><a href="', page['dotdot'], 'block/', blockhash, '">', height, '</a></td>',
		 '<td><a href="', page['dotdot'], 'tx/', txhash, '">', txhash[:10], '...</a></td>',                 
		 '<td style="max-width: 600px;word-wrap:break-word;">', txcomment, '</td></tr>']

	   body += ['</table>\n<br /><br />']


    def handle_address(abe, page):
        address = wsgiref.util.shift_path_info(page['env'])
        if address in (None, '') or page['env']['PATH_INFO'] != '':
            raise PageNotFound()

        body = page['body']
        page['title'] = 'Address ' + escape(address)
        version, binaddr = util.decode_check_address(address)
        if binaddr is None:
            body += ['<p>Not a valid address.</p>']
            return

        dbhash = abe.store.binin(binaddr)

        chains = {}
        balance = {}
        received = {}
        sent = {}
        count = [0, 0]
        chain_ids = []
        def adj_balance(txpoint):
            chain_id = txpoint['chain_id']
            value = txpoint['value']
            if chain_id not in balance:
                chain_ids.append(chain_id)
                chains[chain_id] = abe.chain_lookup_by_id(chain_id)
                balance[chain_id] = 0
                received[chain_id] = 0
                sent[chain_id] = 0
            balance[chain_id] += value
            if value > 0:
                received[chain_id] += value
            else:
                sent[chain_id] -= value
            count[txpoint['is_in']] += 1

        txpoints = []
        max_rows = abe.address_history_rows_max
        in_rows = abe.store.selectall("""
            SELECT
                b.block_nTime,
                cc.chain_id,
                b.block_height,
                1,
                b.block_hash,
                tx.tx_hash,
                txin.txin_pos,
                -prevout.txout_value
              FROM chain_candidate cc
              JOIN block b ON (b.block_id = cc.block_id)
              JOIN block_tx ON (block_tx.block_id = b.block_id)
              JOIN tx ON (tx.tx_id = block_tx.tx_id)
              JOIN txin ON (txin.tx_id = tx.tx_id)
              JOIN txout prevout ON (txin.txout_id = prevout.txout_id)
              JOIN pubkey ON (pubkey.pubkey_id = prevout.pubkey_id)
             WHERE pubkey.pubkey_hash = ?
               AND cc.in_longest = 1""" + ("" if max_rows < 0 else """
             LIMIT ?"""),
                      (dbhash,)
                      if max_rows < 0 else
                      (dbhash, max_rows + 1))

        too_many = False
        if max_rows >= 0 and len(in_rows) > max_rows:
            too_many = True

        #this should fail more gracefully
        if not too_many:
            out_rows = abe.store.selectall("""
                SELECT
                    b.block_nTime,
                    cc.chain_id,
                    b.block_height,
                    0,
                    b.block_hash,
                    tx.tx_hash,
                    txout.txout_pos,
                    txout.txout_value
                  FROM chain_candidate cc
                  JOIN block b ON (b.block_id = cc.block_id)
                  JOIN block_tx ON (block_tx.block_id = b.block_id)
                  JOIN tx ON (tx.tx_id = block_tx.tx_id)
                  JOIN txout ON (txout.tx_id = tx.tx_id)
                  JOIN pubkey ON (pubkey.pubkey_id = txout.pubkey_id)
                 WHERE pubkey.pubkey_hash = ?
                   AND cc.in_longest = 1""" + ("" if max_rows < 0 else """
                 LIMIT ?"""),
                          (dbhash, max_rows + 1)
                          if max_rows >= 0 else
                          (dbhash,))
            if max_rows >= 0 and len(out_rows) > max_rows:
                too_many = True

        if too_many:
            body += ["<p>I'm sorry, this address has too many records"
                     " to display.</p>"]
            return

        rows = []
        rows += in_rows
        rows += out_rows
        rows.sort()
        for row in rows:
            nTime, chain_id, height, is_in, blk_hash, tx_hash, pos, value = row
            txpoint = {
                    "nTime":    int(nTime),
                    "chain_id": int(chain_id),
                    "height":   int(height),
                    "is_in":    int(is_in),
                    "blk_hash": abe.store.hashout_hex(blk_hash),
                    "tx_hash":  abe.store.hashout_hex(tx_hash),
                    "pos":      int(pos),
                    "value":    int(value),
                    }
            adj_balance(txpoint)
            txpoints.append(txpoint)

        if (not chain_ids):
            body += ['<p>Address not seen on the network.</p>']
            return

        def format_amounts(amounts, link):
            ret = []
            for chain_id in chain_ids:
                chain = chains[chain_id]
                if chain_id != chain_ids[0]:
                    ret += [', ']
                ret += [format_satoshis(amounts[chain_id], chain),
                        ' ', escape(chain['code3'])]
                if link:
                    other = util.hash_to_address(
                        chain['address_version'], binaddr)
                    if other != address:
                        ret[-1] = ['<a href="', page['dotdot'],
                                   'address/', other,
                                   '">', ret[-1], '</a>']
            return ret

        if abe.shortlink_type == "firstbits":
            link = abe.store.get_firstbits(
                address_version=version, db_pubkey_hash=dbhash,
                chain_id = (page['chain'] and page['chain']['id']))
            if link:
                link = link.replace('l', 'L')
            else:
                link = address
        else:
            link = address[0 : abe.shortlink_type]
        #body += abe.short_link(page, 'a/' + link)

        #body += ['<p>Balance: '] + format_amounts(balance, True)

        for chain_id in chain_ids:
            balance[chain_id] = 0  # Reset for history traversal.
        
        display_transactions = {}
        display_transactions['address'] = address
        display_transactions['transactions_in'] = count[0]
        display_transactions['transactions_out'] = count[1]
        display_transactions['received'] = format_amounts(received, False)
        display_transactions['sent'] = format_amounts(sent, False)
        display_transactions['balance'] = format_amounts(balance, True)
        
        display_transactions['transaction_list'] = []

        for elt in txpoints:
            chain = chains[elt['chain_id']]
            balance[elt['chain_id']] += elt['value']
            
            transaction = {}
            
            #address
            transaction['tx_hash'] = elt['tx_hash']
            
            #block
            transaction['block_hash'] = elt['blk_hash']
            transaction['block_number'] = elt['height']
            transaction['block_time'] = format_time(elt['nTime'])
            
            #body += ['<tr><td><a href="../tx/', elt['tx_hash'],
            #         '#', 'i' if elt['is_in'] else 'o', elt['pos'],
            #         '">', elt['tx_hash'][:10], '...</a>',
            #         '</td><td><a href="../block/', elt['blk_hash'],
            #         '">', elt['height'], '</a></td><td>',
            #         format_time(elt['nTime']), '</td><td>']
            
            #value
            
            transaction['value'] = ""
            if elt['value'] < 0:
                transaction['value'] += '(%s)' % format_satoshis(-elt['value'], 
                                                                chain)
            else:
                transaction['value'] += '%s' % format_satoshis(elt['value'], 
                                                                chain)
                
            #transaction['balance'] = format_satoshis(balance[elt['chain_id']], 
            #                                        chain)
            transaction['balance'] = format_satoshis(balance[elt['chain_id']], 
                                                    chain)
            
            display_transactions['transaction_list'].append(transaction)
        
        body += view_templates.generate_address_view(display_transactions)
            

    
        

    #search is currently the worst.  rudimentary for now, may be worth fixing.
    def handle_search(abe, page):
        page['title'] = 'Search'
        q = (page['params'].get('q') or [''])[0]
        error = None
        found = None
        if q == '':
            error = "Please enter search terms."
            page['body'] = [
                '<p>Please enter search terms.</p>\n', \
                view_templates.show_search_results(error, found)]
            return

        found = {}
        if HEIGHT_RE.match(q):      
            found['blocks'] = abe.search_number(int(q))
        if util.possible_address(q):
            found['address'] = abe.search_address(q)
        elif ADDR_PREFIX_RE.match(q):
            found['addr_prefix'] = abe.search_address_prefix(q)
        if is_hash_prefix(q):
            found['hash_prefix'] = abe.search_hash_prefix(q)
        #found += abe.search_general(q)
#	found += abe.search_txcomment(q)
        
        page['body'] = [view_templates.show_search_results(error, found)]
        return
        #abe.show_search_results(page, found)

    def show_search_results(abe, page, found):
        if not found:
            page['body'] = [
                '<p>No results found.</p>\n', view_templates.search_form(page)]
            return

        if len(found) == 1:
            # Undo shift_path_info.
            sn = posixpath.dirname(page['env']['SCRIPT_NAME'])
            if sn == '/': sn = ''
            page['env']['SCRIPT_NAME'] = sn
            page['env']['PATH_INFO'] = '/' + page['dotdot'] + found[0]['uri']
            del(page['env']['QUERY_STRING'])
            raise Redirect()

        body = page['body']
        body += ['<h3>Search Results</h3>\n<ul>\n']
        for result in found:
            body += [
                '<li><a href="', page['dotdot'], escape(result['uri']), '">',
                escape(result['name']), '</a></li>\n']
        body += ['</ul>\n']
    
    def get_cold_storage(abe):
        cold_storage_wallets = {}
        cold_storage_data = abe.store.selectall("""
            SELECT cs.base58_address, cs.chain_id
            FROM cold_storage cs
            WHERE is_active=1
        """)
	    
        total_cold_storage_coins=0
        for row in cold_storage_data:
            
            address = row[0]
            chainid = row[1]
            if not util.possible_address(address):
                addrbal= 'ERROR: Address invalid'
            else:
                version, hash = util.decode_address(address)
                addrbal = abe.store.get_balance(chainid, hash)
                total_cold_storage_coins += addrbal
                
                #capture the row detail for the cold storage wallet table
                cold_storage_wallets[address]=addrbal 
        cold_storage_wallets["Total"] = total_cold_storage_coins
        return cold_storage_wallets
			    
    def search_number(abe, n):
        def process(row):
            (chain_name, dbhash, in_longest) = row
            hexhash = abe.store.hashout_hex(dbhash)
            if in_longest == 1:
                name = str(n)
            else:
                name = hexhash
            return {
                'name': 'Block ' + name,
                'uri': 'block/' + hexhash,
                }

        return map(process, abe.store.selectall("""
            SELECT c.chain_name, b.block_hash, cc.in_longest
              FROM chain c
              JOIN chain_candidate cc ON (cc.chain_id = c.chain_id)
              JOIN block b ON (b.block_id = cc.block_id)
             WHERE cc.block_height = ?
             ORDER BY c.chain_name, cc.in_longest DESC
        """, (n,)))

    def search_hash_prefix(abe, q, types = ('tx', 'block', 'pubkey')):
        q = q.lower()
        ret = []
        for t in types:
            def process(row):
                if   t == 'tx':    name = 'Transaction'
                elif t == 'block': name = 'Block'
                else:
                    # XXX Use Bitcoin address version until we implement
                    # /pubkey/... for this to link to.
                    return abe._found_address(
                        util.hash_to_address('\0', abe.store.binout(row[0])))
                hash = abe.store.hashout_hex(row[0])
                return {
                    'name': name + ' ' + hash,
                    'uri': t + '/' + hash,
                    }

            if t == 'pubkey':
                if len(q) > 40:
                    continue
                lo = abe.store.binin_hex(q + '0' * (40 - len(q)))
                hi = abe.store.binin_hex(q + 'f' * (40 - len(q)))
            else:
                lo = abe.store.hashin_hex(q + '0' * (64 - len(q)))
                hi = abe.store.hashin_hex(q + 'f' * (64 - len(q)))

            ret += map(process, abe.store.selectall(
                "SELECT " + t + "_hash FROM " + t + " WHERE " + t +
                # XXX hardcoded limit.
                "_hash BETWEEN ? AND ? LIMIT 100",
                (lo, hi)))
        return ret

    def _found_address(abe, address):
        return { 'name': 'Address ' + address, 'uri': 'address/' + address }

    def search_address(abe, address):
        try:
            binaddr = base58.bc_address_to_hash_160(address)
        except:
            return abe.search_address_prefix(address)
        return [abe._found_address(address)]

    def search_address_prefix(abe, ap):
        ret = []
        ones = 0
        for c in ap:
            if c != '1':
                break
            ones += 1
        all_ones = (ones == len(ap))
        minlen = max(len(ap), 24)
        l = max(35, len(ap))  # XXX Increase "35" to support multibyte
                              # address versions.
        al = ap + ('1' * (l - len(ap)))
        ah = ap + ('z' * (l - len(ap)))

        def incr_str(s):
            for i in range(len(s)-1, -1, -1):
                if s[i] != '\xff':
                    return s[:i] + chr(ord(s[i])+1) + ('\0' * (len(s) - i - 1))
            return '\1' + ('\0' * len(s))

        def process(row):
            hash = abe.store.binout(row[0])
            address = util.hash_to_address(vl, hash)
            if address.startswith(ap):
                v = vl
            else:
                if vh != vl:
                    address = util.hash_to_address(vh, hash)
                    if not address.startswith(ap):
                        return None
                    v = vh
            if abe.is_address_version(v):
                return abe._found_address(address)

        while l >= minlen:
            vl, hl = util.decode_address(al)
            vh, hh = util.decode_address(ah)
            if ones:
                if not all_ones and \
                        util.hash_to_address('\0', hh)[ones:][:1] == '1':
                    break
            elif vh == '\0':
                break
            elif vh != vl and vh != incr_str(vl):
                continue
            if hl <= hh:
                neg = ""
            else:
                neg = " NOT"
                hl, hh = hh, hl
            bl = abe.store.binin(hl)
            bh = abe.store.binin(hh)
            ret += filter(None, map(process, abe.store.selectall(
                "SELECT pubkey_hash FROM pubkey WHERE pubkey_hash" +
                # XXX hardcoded limit.
                neg + " BETWEEN ? AND ? LIMIT 100", (bl, bh))))
            l -= 1
            al = al[:-1]
            ah = ah[:-1]

        return ret

    def search_general(abe, q):
        """Search for something that is not an address, hash, or block number.
        Currently, this is limited to chain names and currency codes."""
        def process(row):
            (name, code3) = row
            return { 'name': name + ' (' + code3 + ')',
                     'uri': 'chain/' + str(name) }
        ret = map(process, abe.store.selectall("""
            SELECT chain_name, chain_code3
              FROM chain
             WHERE UPPER(chain_name) LIKE '%' || ? || '%'
                OR UPPER(chain_code3) LIKE '%' || ? || '%'
        """, (q.upper(), q.upper())))
        return ret

    def search_txcomment(abe, q):
        """Search for transactions by transaction comments. Search is not case sensitive."""
        def process(row):
            (transhash, txid) = row
            return { 'name': 'Transaction  ' + str(transhash),
                     'uri': 'tx/' + str(transhash) }
        ret = map(process, abe.store.selectall("""
            SELECT tx_hash, tx_id
              FROM tx
             WHERE UPPER(tx_comment) LIKE '%' || ? || '%'
        """, (q.upper())))
        return ret


    def handle_t(abe, page):
        abe.show_search_results(
            page,
            abe.search_hash_prefix(
                b58hex(wsgiref.util.shift_path_info(page['env'])),
                ('tx',)))


    #currently broken - removing for now
    def handle_b(abe, page):
        if 'chain' in page:
            chain = page['chain']
            print "CHAIN %s" % chain
            height = wsgiref.util.shift_path_info(page['env'])
            print "height %s" % height
            
            try:
                height = int(height)
            except:
                raise PageNotFound()
            if height < 0 or page['env']['PATH_INFO'] != '':
                raise PageNotFound()

            cmd = wsgiref.util.shift_path_info(page['env'])
            if cmd is not None:
                raise PageNotFound()  # XXX want to support /a/...

            page['title'] = [escape(chain['name']), ' ', height]
            abe._show_block(
                'chain_id = ? AND block_height = ? AND in_longest = 1',
                (chain['id'], height), page, page['dotdot'] + 'block/', chain)
            return

        abe.show_search_results(
            page,
            abe.search_hash_prefix(
                shortlink_block(wsgiref.util.shift_path_info(page['env'])),
                ('block',)))

    def handle_a(abe, page):
        arg = wsgiref.util.shift_path_info(page['env'])
        if abe.shortlink_type == "firstbits":
            addrs = map(
                abe._found_address,
                abe.store.firstbits_to_addresses(
                    arg.lower(),
                    chain_id = page['chain'] and page['chain']['id']))
        else:
            addrs = abe.search_address_prefix(arg)
        abe.show_search_results(page, addrs)

    def handle_unspent(abe, page):
        abe.do_raw(page, abe.do_unspent)

    def do_unspent(abe, page, chain):
        addrs = wsgiref.util.shift_path_info(page['env'])
        if addrs is None:
            addrs = []
        else:
            addrs = addrs.split("|");
        if len(addrs) < 1 or len(addrs) > MAX_UNSPENT_ADDRESSES:
            return 'Number of addresses must be between 1 and ' + \
                str(MAX_UNSPENT_ADDRESSES)

        if chain:
            chain_id = chain['id']
            bind = [chain_id]
        else:
            chain_id = None
            bind = []

        hashes = []
        good_addrs = []
        for address in addrs:
            try:
                hashes.append(abe.store.binin(
                        base58.bc_address_to_hash_160(address)))
                good_addrs.append(address)
            except:
                pass
        addrs = good_addrs
        bind += hashes

        if len(hashes) == 0:  # Address(es) are invalid.
            return 'Error getting unspent outputs'  # blockchain.info compatible

        placeholders = "?" + (",?" * (len(hashes)-1))

        max_rows = abe.address_history_rows_max
        if max_rows >= 0:
            bind += [max_rows + 1]

        spent = set()
        for txout_id, spent_chain_id in abe.store.selectall("""
            SELECT txin.txout_id, cc.chain_id
              FROM chain_candidate cc
              JOIN block_tx ON (block_tx.block_id = cc.block_id)
              JOIN txin ON (txin.tx_id = block_tx.tx_id)
              JOIN txout prevout ON (txin.txout_id = prevout.txout_id)
              JOIN pubkey ON (pubkey.pubkey_id = prevout.pubkey_id)
             WHERE cc.in_longest = 1""" + ("" if chain_id is None else """
               AND cc.chain_id = ?""") + """
               AND pubkey.pubkey_hash IN (""" + placeholders + """)""" + (
                "" if max_rows < 0 else """
             LIMIT ?"""), bind):
            spent.add((int(txout_id), int(spent_chain_id)))

        abe.log.debug('spent: %s', spent)

        received_rows = abe.store.selectall("""
            SELECT
                txout.txout_id,
                cc.chain_id,
                tx.tx_hash,
                txout.txout_pos,
                txout.txout_scriptPubKey,
                txout.txout_value,
                cc.block_height
              FROM chain_candidate cc
              JOIN block_tx ON (block_tx.block_id = cc.block_id)
              JOIN tx ON (tx.tx_id = block_tx.tx_id)
              JOIN txout ON (txout.tx_id = tx.tx_id)
              JOIN pubkey ON (pubkey.pubkey_id = txout.pubkey_id)
             WHERE cc.in_longest = 1""" + ("" if chain_id is None else """
               AND cc.chain_id = ?""") + """
               AND pubkey.pubkey_hash IN (""" + placeholders + """)""" + (
                "" if max_rows < 0 else """
             ORDER BY cc.block_height,
                   block_tx.tx_pos,
                   txout.txout_pos
             LIMIT ?"""), bind)

        if max_rows >= 0 and len(received_rows) > max_rows:
            return "ERROR: too many records to process"

        rows = []
        for row in received_rows:
            key = (int(row[0]), int(row[1]))
            if key in spent:
                continue
            rows.append(row[2:])

        if len(rows) == 0:
            return 'No free outputs to spend [' + '|'.join(addrs) + ']'

        out = []
        for row in rows:
            tx_hash, out_pos, script, value, height = row
            tx_hash = abe.store.hashout_hex(tx_hash)
            out_pos = None if out_pos is None else int(out_pos)
            script = abe.store.binout_hex(script)
            value = None if value is None else int(value)
            height = None if height is None else int(height)
            out.append({
                    'tx_hash': tx_hash,
                    'tx_output_n': out_pos,
                    'script': script,
                    'value': value,
                    'value_hex': None if value is None else "%x" % value,
                    'block_number': height})

        return json.dumps({ 'unspent_outputs': out }, sort_keys=True, indent=2)

    def do_raw(abe, page, func):
        page['content_type'] = 'text/plain'
        page['template'] = '%(body)s'
        page['body'] = func(page, page['chain'])

    def handle_q(abe, page):
        cmd = wsgiref.util.shift_path_info(page['env'])
        if cmd is None:
            return abe.q(page)

        func = getattr(abe, 'q_' + cmd, None)
        if func is None:
            raise PageNotFound()

        abe.do_raw(page, func)

        if page['content_type'] == 'text/plain':
            jsonp = page['params'].get('jsonp', [None])[0]
            fmt = page['params'].get('format', ["jsonp" if jsonp else "csv"])[0]

            if fmt in ("json", "jsonp"):
                page['body'] = json.dumps([page['body']])

                if fmt == "jsonp":
                    page['body'] = (jsonp or "jsonp") + "(" + page['body'] + ")"
                    page['content_type'] = 'application/javascript'
                else:
                    page['content_type'] = 'application/json'

    def q(abe, page):
        page['body'] = ['<p>Supported APIs:</p>\n<ul>\n']
        for name in dir(abe):
            if not name.startswith("q_"):
                continue
            cmd = name[2:]
            page['body'] += ['<li><a href="q/', cmd, '">', cmd, '</a>']
            val = getattr(abe, name)
            if val.__doc__ is not None:
                page['body'] += [' - ', escape(val.__doc__)]
            page['body'] += ['</li>\n']
        page['body'] += ['</ul>\n']

    def get_max_block_height(abe, chain):
        # "getblockcount" traditionally returns max(block_height),
        # which is one less than the actual block count.
        return abe.store.get_block_number(chain['id'])

    def q_getblockcount(abe, page, chain):
        """shows the current block number."""
        if chain is None:
            return 'Shows the greatest block height in CHAIN.\n' \
                '/chain/CHAIN/q/getblockcount\n'
        return abe.get_max_block_height(chain)

    def q_getdifficulty(abe, page, chain):
        """shows the last solved block's difficulty."""
        if chain is None:
            return 'Shows the difficulty of the last block in CHAIN.\n' \
                '/chain/CHAIN/q/getdifficulty\n'
        target = abe.store.get_target(chain['id'])
        return "" if target is None else util.target_to_difficulty(target)

    def q_translate_address(abe, page, chain):
        """shows the address in a given chain with a given address's hash."""
        addr = wsgiref.util.shift_path_info(page['env'])
        if chain is None or addr is None:
            return 'Translates ADDRESS for use in CHAIN.\n' \
                '/chain/CHAIN/q/translate_address/ADDRESS\n'
        version, hash = util.decode_check_address(addr)
        if hash is None:
            return addr + " (INVALID ADDRESS)"
        return util.hash_to_address(chain['address_version'], hash)

    def q_decode_address(abe, page, chain):
        """shows the version prefix and hash encoded in an address."""
        addr = wsgiref.util.shift_path_info(page['env'])
        if addr is None:
            return "Shows ADDRESS's version byte(s) and public key hash" \
                ' as hex strings separated by colon (":").\n' \
                '/q/decode_address/ADDRESS\n'
        # XXX error check?
        version, hash = util.decode_address(addr)
        ret = version.encode('hex') + ":" + hash.encode('hex')
        if util.hash_to_address(version, hash) != addr:
            ret = "INVALID(" + ret + ")"
        return ret

    def q_addresstohash(abe, page, chain):
        """shows the public key hash encoded in an address."""
        addr = wsgiref.util.shift_path_info(page['env'])
        if addr is None:
            return 'Shows the 160-bit hash encoded in ADDRESS.\n' \
                'For BBE compatibility, the address is not checked for' \
                ' validity.  See also /q/decode_address.\n' \
                '/q/addresstohash/ADDRESS\n'
        version, hash = util.decode_address(addr)
        return hash.encode('hex').upper()

    def q_hashtoaddress(abe, page, chain):
        """shows the address with the given version prefix and hash."""
        arg1 = wsgiref.util.shift_path_info(page['env'])
        arg2 = wsgiref.util.shift_path_info(page['env'])
        if arg1 is None:
            return \
                'Converts a 160-bit hash and address version to an address.\n' \
                '/q/hashtoaddress/HASH[/VERSION]\n'

        if page['env']['PATH_INFO']:
            return "ERROR: Too many arguments"

        if arg2 is not None:
            # BBE-compatible HASH/VERSION
            version, hash = arg2, arg1

        elif arg1.find(":") >= 0:
            # VERSION:HASH as returned by /q/decode_address.
            version, hash = arg1.split(":", 1)

        elif chain:
            version, hash = chain['address_version'].encode('hex'), arg1

        else:
            # Default: Bitcoin address starting with "1".
            version, hash = '00', arg1

        try:
            hash = hash.decode('hex')
            version = version.decode('hex')
        except:
            return 'ERROR: Arguments must be hexadecimal strings of even length'
        return util.hash_to_address(version, hash)

    def q_hashpubkey(abe, page, chain):
        """shows the 160-bit hash of the given public key."""
        pubkey = wsgiref.util.shift_path_info(page['env'])
        if pubkey is None:
            return \
                "Returns the 160-bit hash of PUBKEY.\n" \
                "For example, the Bitcoin genesis block's output public key," \
                " seen in its transaction output scriptPubKey, starts with\n" \
                "04678afdb0fe..., and its hash is" \
                " 62E907B15CBF27D5425399EBF6F0FB50EBB88F18, corresponding" \
                " to address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa.\n" \
                "/q/hashpubkey/PUBKEY\n"
        try:
            pubkey = pubkey.decode('hex')
        except:
            return 'ERROR: invalid hexadecimal byte string.'
        return util.pubkey_to_hash(pubkey).encode('hex').upper()

    def q_checkaddress(abe, page, chain):
        """checks an address for validity."""
        addr = wsgiref.util.shift_path_info(page['env'])
        if addr is None:
            return \
                "Returns the version encoded in ADDRESS as a hex string.\n" \
                "If ADDRESS is invalid, returns either X5, SZ, or CK for" \
                " BBE compatibility.\n" \
                "/q/checkaddress/ADDRESS\n"
        if util.possible_address(addr):
            version, hash = util.decode_address(addr)
            if util.hash_to_address(version, hash) == addr:
                return version.encode('hex').upper()
            return 'CK'
        if len(addr) >= 26:
            return 'X5'
        return 'SZ'

    def q_nethash(abe, page, chain):
        """shows statistics about difficulty and network power."""
        if chain is None:
            return 'Shows statistics every INTERVAL blocks.\n' \
                'Negative values count back from the last block.\n' \
                '/chain/CHAIN/q/nethash[/INTERVAL[/START[/STOP]]]\n'

        jsonp = page['params'].get('jsonp', [None])[0]
        fmt = page['params'].get('format', ["jsonp" if jsonp else "csv"])[0]
        interval = path_info_int(page, 144)
        start = path_info_int(page, 0)
        stop = path_info_int(page, None)

        if stop == 0:
            stop = None

        if interval < 0 and start != 0:
            return 'ERROR: Negative INTERVAL requires 0 START.'

        if interval < 0 or start < 0 or (stop is not None and stop < 0):
            count = abe.get_max_block_height(chain)
            if start < 0:
                start += count
            if stop is not None and stop < 0:
                stop += count
            if interval < 0:
                interval = -interval
                start = count - (count / interval) * interval

        # Select every INTERVAL blocks from START to STOP.
        # Standard SQL lacks an "every Nth row" feature, so we
        # provide it with the help of a table containing the integers.
        # We don't need all integers, only as many as rows we want to
        # fetch.  We happen to have a table with the desired integers,
        # namely chain_candidate; its block_height column covers the
        # required range without duplicates if properly constrained.
        # That is the story of the second JOIN.

        if stop is not None:
            stop_ix = (stop - start) / interval

        rows = abe.store.selectall("""
            SELECT b.block_height,
                   b.block_nTime,
                   b.block_chain_work,
                   b.block_nBits
              FROM block b
              JOIN chain_candidate cc ON (cc.block_id = b.block_id)
              JOIN chain_candidate ints ON (
                       ints.chain_id = cc.chain_id
                   AND ints.in_longest = 1
                   AND ints.block_height * ? + ? = cc.block_height)
             WHERE cc.in_longest = 1
               AND cc.chain_id = ?""" + (
                "" if stop is None else """
               AND ints.block_height <= ?""") + """
             ORDER BY cc.block_height""",
                                   (interval, start, chain['id'])
                                   if stop is None else
                                   (interval, start, chain['id'], stop_ix))
        if fmt == "csv":
            ret = NETHASH_HEADER

        elif fmt in ("json", "jsonp"):
            ret = []

        elif fmt == "svg":
            page['template'] = NETHASH_SVG_TEMPLATE
            ret = ""

        else:
            return "ERROR: unknown format: " + fmt

        prev_nTime, prev_chain_work = 0, -1

        for row in rows:
            height, nTime, chain_work, nBits = row
            nTime            = float(nTime)
            nBits            = int(nBits)
            target           = util.calculate_target(nBits)
            difficulty       = util.target_to_difficulty(target)
            work             = util.target_to_work(target)
            chain_work       = abe.store.binout_int(chain_work) - work

            if row is not rows[0] or fmt == "svg":
                height           = int(height)
                interval_work    = chain_work - prev_chain_work
                avg_target       = util.work_to_target(
                    interval_work / float(interval))
                #if avg_target == target - 1:
                #    avg_target = target
                interval_seconds = nTime - prev_nTime
                if interval_seconds <= 0:
                    nethash = 'Infinity'
                else:
                    nethash = "%.0f" % (interval_work / interval_seconds,)

                if fmt == "csv":
                    ret += "%d,%d,%d,%d,%.3f,%d,%.0f,%s\n" % (
                        height, nTime, target, avg_target, difficulty, work,
                        interval_seconds / interval, nethash)

                elif fmt in ("json", "jsonp"):
                    ret.append([
                            height, int(nTime), target, avg_target,
                            difficulty, work, chain_work])

                elif fmt == "svg":
                    ret += '<abe:nethash t="%d" d="%.3f"' \
                        ' w="%d"/>\n' % (nTime, difficulty, interval_work)

            prev_nTime, prev_chain_work = nTime, chain_work

        if fmt == "csv":
            return ret

        elif fmt == "json":
            page['content_type'] = 'application/json'
            return json.dumps(ret)

        elif fmt == "jsonp":
            page['content_type'] = 'application/javascript'
            return (jsonp or "jsonp") + "(" + json.dumps(ret) + ")"

        elif fmt == "svg":
            page['content_type'] = 'image/svg+xml'
            return ret

    def q_totalbc(abe, page, chain):
        """shows the amount of currency ever mined."""
        if chain is None:
            return 'Shows the amount of currency ever mined.\n' \
                'This differs from the amount in circulation when' \
                ' coins are destroyed, as happens frequently in Namecoin.\n' \
                'Unlike http://blockexplorer.com/q/totalbc, this does not' \
                ' support future block numbers, and it returns a sum of' \
                ' observed generations rather than a calculated value.\n' \
                '/chain/CHAIN/q/totalbc[/HEIGHT]\n'
        height = path_info_uint(page, None)
        if height is None:
            row = abe.store.selectrow("""
                SELECT b.block_total_satoshis
                  FROM chain c
                  LEFT JOIN block b ON (c.chain_last_block_id = b.block_id)
                 WHERE c.chain_id = ?
            """, (chain['id'],))
        else:
            row = abe.store.selectrow("""
                SELECT b.block_total_satoshis
                  FROM chain_candidate cc
                  LEFT JOIN block b ON (b.block_id = cc.block_id)
                 WHERE cc.chain_id = ?
                   AND cc.block_height = ?
                   AND cc.in_longest = 1
            """, (chain['id'], height))
            if not row:
                return 'ERROR: block %d not seen yet' % (height,)
        return format_satoshis(row[0], chain) if row else 0

    def q_totalbccirc(abe, page, chain):
        """shows the amount of currency in circulation."""
        if chain is None:
            return 'Shows the amount of currency in circulation.\n' \
                'This is calculated as total coins created minus total coins held ' \
                'in cold storage. All cold storage wallet addresses are documented on the ' \
		'ABE home page.  Any coins destroyed are not taken into account. \n' \
                'This does not support future or previous block numbers, and it returns a sum of' \
                ' observed generations minus a calculated sum value for cold storage address balances.\n' \
                '/chain/CHAIN/q/totalbccirc\n'
        height = path_info_uint(page, None) 

    	rows = abe.store.selectall("""
	   SELECT b.block_total_satoshis, cs.base58_address
              FROM chain c
              LEFT JOIN block b ON (c.chain_last_block_id = b.block_id)
              LEFT JOIN cold_storage cs ON (c.chain_id = cs.chain_id and cs.is_active=1)
	      WHERE c.chain_id = ?
	""", (chain['id'],))

	totalmined = 0
        totalcold = 0
	prevtotal= 0
        for row in rows:
	   totalmined = row[0]
	   if row[1]:
	      address = row[1]
	   else:
	      address = "NoAddressFound"
	   if not util.possible_address(address):
	      addrbal= 0
           else:
	      version, hash = util.decode_address(address)
              addrbal = abe.store.get_balance(chain['id'], hash)
	      totalcold = addrbal+prevtotal
              prevtotal = totalcold

	return format_satoshis((totalmined-totalcold), chain) if rows else 0

    def q_getreceivedbyaddress(abe, page, chain):
        """shows the amount ever received by a given address."""
        addr = wsgiref.util.shift_path_info(page['env'])
        if chain is None or addr is None:
            return 'returns amount of money received by given address (not balance, sends are not subtracted)\n' \
                '/chain/CHAIN/q/getreceivedbyaddress/ADDRESS\n'

        if not util.possible_address(addr):
            return 'ERROR: address invalid'

        version, hash = util.decode_address(addr)
        return format_satoshis(abe.store.get_received(chain['id'], hash), chain)

    def q_getsentbyaddress(abe, page, chain):
        """shows the amount ever sent from a given address."""
        addr = wsgiref.util.shift_path_info(page['env'])
        if chain is None or addr is None:
            return 'returns amount of money sent from given address\n' \
                '/chain/CHAIN/q/getsentbyaddress/ADDRESS\n'

        if not util.possible_address(addr):
            return 'ERROR: address invalid'

        version, hash = util.decode_address(addr)
        return format_satoshis(abe.store.get_sent(chain['id'], hash), chain)

    def q_addressbalance(abe, page, chain):
        """amount ever received minus amount ever sent by a given address."""
        addr = wsgiref.util.shift_path_info(page['env'])
        if chain is None or addr is None:
            return 'returns amount of money at the given address\n' \
                '/chain/CHAIN/q/addressbalance/ADDRESS\n'

        if not util.possible_address(addr):
            return 'ERROR: address invalid'

        version, hash = util.decode_address(addr)
        total = abe.store.get_balance(chain['id'], hash)

        return ("ERROR: please try again" if total is None else
                format_satoshis(total, chain))

    def q_fb(abe, page, chain):
        """returns an address's firstbits."""

        if not abe.store.use_firstbits:
            raise PageNotFound()

        addr = wsgiref.util.shift_path_info(page['env'])
        if addr is None:
            return 'Shows ADDRESS\'s firstbits:' \
                ' the shortest initial substring that uniquely and' \
                ' case-insensitively distinguishes ADDRESS from all' \
                ' others first appearing before it or in the same block.\n' \
                'See http://firstbits.com/.\n' \
                'Returns empty if ADDRESS has no firstbits.\n' \
                '/chain/CHAIN/q/fb/ADDRESS\n' \
                '/q/fb/ADDRESS\n'

        if not util.possible_address(addr):
            return 'ERROR: address invalid'

        version, dbhash = util.decode_address(addr)
        ret = abe.store.get_firstbits(
            address_version = version,
            db_pubkey_hash = abe.store.binin(dbhash),
            chain_id = (chain and chain['id']))

        if ret is None:
            return 'ERROR: address not in the chain.'

        return ret

    def q_addr(abe, page, chain):
        """returns the full address having the given firstbits."""

        if not abe.store.use_firstbits:
            raise PageNotFound()

        fb = wsgiref.util.shift_path_info(page['env'])
        if fb is None:
            return 'Shows the address identified by FIRSTBITS:' \
                ' the first address in CHAIN to start with FIRSTBITS,' \
                ' where the comparison is case-insensitive.\n' \
                'See http://firstbits.com/.\n' \
                'Returns the argument if none matches.\n' \
                '/chain/CHAIN/q/addr/FIRSTBITS\n' \
                '/q/addr/FIRSTBITS\n'

        return "\n".join(abe.store.firstbits_to_addresses(
                fb, chain_id = (chain and chain['id'])))

    def handle_download(abe, page):
        name = abe.args.download_name
        if name is None:
            name = re.sub(r'\W+', '-', ABE_APPNAME.lower()) + '-' + ABE_VERSION
        fileobj = lambda: None
        fileobj.func_dict['write'] = page['start_response'](
            '200 OK',
            [('Content-type', 'application/x-gtar-compressed'),
             ('Content-disposition', 'filename=' + name + '.tar.gz')])
        import tarfile
        with tarfile.TarFile.open(fileobj=fileobj, mode='w|gz',
                                  format=tarfile.PAX_FORMAT) as tar:
            tar.add(os.path.split(__file__)[0], name)
        raise Streamed()

    def serve_static(abe, path, start_response):
        slen = len(abe.static_path)
        if path[:slen] != abe.static_path:
            raise PageNotFound()
        path = path[slen:]
        try:
            # Serve static content.
            # XXX Should check file modification time and handle HTTP
            # if-modified-since.  Or just hope serious users will map
            # our htdocs as static in their web server.
            # XXX is "+ '/' + path" adequate for non-POSIX systems?
            found = open(abe.htdocs + '/' + path, "rb")
            import mimetypes
            type, enc = mimetypes.guess_type(path)
            # XXX Should do something with enc if not None.
            # XXX Should set Content-length.
            start_response('200 OK', [('Content-type', type or 'text/plain')])
            return found
        except IOError:
            raise PageNotFound()

    # Change this if you want empty or multi-byte address versions.
    def is_address_version(abe, v):
        return len(v) == 1

    def short_link(abe, page, link):
        base = abe.base_url
        if base is None:
            env = page['env'].copy()
            env['SCRIPT_NAME'] = posixpath.normpath(
                posixpath.dirname(env['SCRIPT_NAME'] + env['PATH_INFO'])
                + '/' + page['dotdot'])
            env['PATH_INFO'] = link
            full = wsgiref.util.request_uri(env)
        else:
            full = base + link

        return ['<p class="shortlink">Short Link: <a href="',
                page['dotdot'], link, '">', full, '</a></p>\n']

    def fix_path_info(abe, env):
        ret = True
        pi = env['PATH_INFO']
        pi = posixpath.normpath(pi)
        if pi[-1] != '/' and env['PATH_INFO'][-1] == '/':
            pi += '/'
        if pi == '/':
            pi += abe.home
            if not '/' in abe.home:
                ret = False
        if pi == env['PATH_INFO']:
            ret = False
        else:
            env['PATH_INFO'] = pi
        return ret

def find_htdocs():
    return os.path.join(os.path.split(__file__)[0], 'htdocs')

def get_int_param(page, name):
    vals = page['params'].get(name)
    return vals and int(vals[0])

def path_info_uint(page, default):
    ret = path_info_int(page, None)
    if ret is None or ret < 0:
        return default
    return ret

def path_info_int(page, default):
    s = wsgiref.util.shift_path_info(page['env'])
    if s is None:
        return default
    try:
        return int(s)
    except ValueError:
        return default

def format_time(nTime):
    import time
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(int(nTime)))

def format_satoshis(satoshis, chain):
    # XXX Should find COIN and LOG10COIN from chain.
    if satoshis is None:
        return ''
    if satoshis < 0:
        return '-' + format_satoshis(-satoshis, chain)
    satoshis = int(satoshis)
    integer = satoshis / COIN
    frac = satoshis % COIN
    return (str(integer) +
            ('.' + (('0' * LOG10COIN) + str(frac))[-LOG10COIN:])
            .rstrip('0').rstrip('.'))

def format_difficulty(diff):
    idiff = int(diff)
    ret = '.%03d' % (int(round((diff - idiff) * 1000)),)
    while idiff > 999:
        ret = (' %03d' % (idiff % 1000,)) + ret
        idiff = idiff / 1000
    return str(idiff) + ret

def hash_to_address_link(version, hash, dotdot):
    if hash == DataStore.NULL_PUBKEY_HASH:
        return 'Destroyed'
    if hash is None:
        return 'UNKNOWN'
    addr = util.hash_to_address(version, hash)
    return ['<a href="', dotdot, 'address/', addr, '">', addr, '</a>']

def decode_script(script):
    if script is None:
        return ''
    try:
        return deserialize.decode_script(script)
    except KeyError, e:
        return 'Nonstandard script'

def b58hex(b58):
    try:
        return base58.b58decode(b58, None).encode('hex_codec')
    except:
        raise PageNotFound()

def hexb58(hex):
    return base58.b58encode(hex.decode('hex_codec'))

def block_shortlink(block_hash):
    zeroes = 0
    for c in block_hash:
        if c == '0':
            zeroes += 1
        else:
            break
    zeroes &= ~1
    return hexb58("%02x%s" % (zeroes / 2, block_hash[zeroes : zeroes+12]))

def shortlink_block(link):
    try:
        data = base58.b58decode(link, None)
    except:
        raise PageNotFound()
    return ('00' * ord(data[0])) + data[1:].encode('hex_codec')

def is_hash_prefix(s):
    return HASH_PREFIX_RE.match(s) and len(s) >= HASH_PREFIX_MIN

def flatten(l):
    if isinstance(l, list):
        return ''.join(map(flatten, l))
    if l is None:
        raise Exception('NoneType in HTML conversion')
    if isinstance(l, unicode):
        return l
    return str(l)

def redirect(page):
    uri = wsgiref.util.request_uri(page['env'])
    page['start_response'](
        '301 Moved Permanently',
        [('Location', uri),
         ('Content-Type', 'text/html')])
    return ('<html><head><title>Moved</title></head>\n'
            '<body><h1>Moved</h1><p>This page has moved to '
            '<a href="' + uri + '">' + uri + '</a></body></html>')

def serve(store):
    
    args = store.args
    abe = Abe(store, args)
    if args.host or args.port:
        # HTTP server.
        if args.host is None:
            args.host = "localhost"
        from wsgiref.simple_server import make_server
        port = int(args.port or 80)
        httpd = make_server(args.host, port, abe)
        abe.log.warning("Listening on http://%s:%d", args.host, port)
        # httpd.shutdown() sometimes hangs, so don't call it.  XXX
        httpd.serve_forever()
    else:
        # FastCGI server.
        from flup.server.fcgi import WSGIServer

        # In the case where the web server starts Abe but can't signal
        # it on server shutdown (because Abe runs as a different user)
        # we arrange the following.  FastCGI script passes its pid as
        # --watch-pid=PID and enters an infinite loop.  We check every
        # minute whether it has terminated and exit when it has.
        wpid = args.watch_pid
        if wpid is not None:
            wpid = int(wpid)
            interval = 60.0  # XXX should be configurable.
            from threading import Timer
            import signal
            def watch():
                if not process_is_alive(wpid):
                    abe.log.warning("process %d terminated, exiting", wpid)
                    #os._exit(0)  # sys.exit merely raises an exception.
                    os.kill(os.getpid(), signal.SIGTERM)
                    return
                abe.log.log(0, "process %d found alive", wpid)
                Timer(interval, watch).start()
            Timer(interval, watch).start()
        WSGIServer(abe).run()

def process_is_alive(pid):
    # XXX probably fails spectacularly on Windows.
    import errno
    try:
        os.kill(pid, 0)
        return True
    except OSError, e:
        if e.errno == errno.EPERM:
            return True  # process exists, but we can't send it signals.
        if e.errno == errno.ESRCH:
            return False # no such process.
        raise

def main(argv):
    print "MAIN"
    
    conf = {
        "port":                     None,
        "host":                     None,
        "no_serve":                 None,
        "no_load":                  None,
        "debug":                    None,
        "static_path":              None,
        "document_root":            None,
        "auto_agpl":                None,
        "download_name":            None,
        "watch_pid":                None,
        "base_url":                 None,
        "logging":                  None,
        "address_history_rows_max": None,
        "shortlink_type":           None,

        "template":     DEFAULT_HOMEPAGE_TEMPLATE,
        "template_vars": {
            "ABE_URL": ABE_URL,
            "APPNAME": ABE_APPNAME,
            "VERSION": ABE_VERSION,
            "COPYRIGHT": COPYRIGHT,
            "COPYRIGHT_YEARS": COPYRIGHT_YEARS,
            "COPYRIGHT_URL": COPYRIGHT_URL,
            "DONATIONS_BTC": DONATIONS_BTC,
            "DONATIONS_NMC": DONATIONS_NMC,
            "CONTENT_TYPE": DEFAULT_CONTENT_TYPE,
            "HOMEPAGE": DEFAULT_HOMEPAGE,
            },
            
        }
    conf.update(DataStore.CONFIG_DEFAULTS)
    
    args, argv = readconf.parse_argv(argv, conf)

    if (args.no_serve and args.no_load):
        sys.stderr.write(
            "Error: You told me not to serve nor to load blocks (--no-serve and --no-load)\n"
            "Nothing to do, have a good day...\n")
        return 1
    elif not argv:
        pass
    elif argv[0] in ('-h', '--help'):
        print ("""Usage: python -m Abe.abe [-h] [--config=FILE] [--CONFIGVAR=VALUE]...

A Bitcoin block chain browser.

  --help                    Show this help message and exit.
  --version                 Show the program version and exit.
  --print-htdocs-directory  Show the static content directory name and exit.
  --config FILE             Read options from FILE.

All configuration variables may be given as command arguments.
See abe.conf for commented examples.""")
        return 0
    elif argv[0] in ('-v', '--version'):
        print ABE_APPNAME, ABE_VERSION
        print "Schema version", DataStore.SCHEMA_VERSION
        return 0
    elif argv[0] == '--print-htdocs-directory':
        print find_htdocs()
        return 0
    else:
        sys.stderr.write(
            "Error: unknown option `%s'\n"
            "See `python -m Abe.abe --help' for more information.\n"
            % (argv[0],))
        return 1

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG,
        format=DEFAULT_LOG_FORMAT)
    if args.logging is not None:
        import logging.config as logging_config
        logging_config.dictConfig(args.logging)

    if args.auto_agpl:
        import tarfile

    store = make_store(args)
    if (not args.no_serve):
        serve(store)
    return 0

if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
