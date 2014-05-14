# -*- coding: utf-8 -*-
##HEADER/FOOTER

def get_default_homepage_template():
    template ="""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <link rel="stylesheet" type="text/css"
         href="%(dotdot)s%(STATIC_PATH)sabe.css" />
        <link rel="shortcut icon" href="%(dotdot)s%(STATIC_PATH)sfavicon.ico" />
        <link rel="stylesheet" href="//netdna.bootstrapcdn.com/bootstrap/3.1.1/css/bootstrap.min.css">
        <title>SolarCoin Blockchain</title>
    </head>
    <body>
      <!-- navbar -->
      <div class="navbar navbar-inverse navbar-static-top" role="navigation">
          <div class="container">
            <div class="navbar-header">
              <button type="button" class="navbar-toggle" data-toggle="collapse" data-target=".navbar-collapse">
                <span class="sr-only">Toggle navigation</span>
                <span class="icon-bar"></span>
                <span class="icon-bar"></span>
                <span class="icon-bar"></span>
              </button>
              <a class="navbar-brand" href="#">SolarCoin Blockchain Explorer</a>
            </div>
            <div class="collapse navbar-collapse">
              <ul class="nav navbar-nav">
                <li><a href="/">Home</a></li>
                <li><a href="/browse_blocks/SolarCoin">Browse Blocks</a></li>
                <li><a href="#about">About</a></li>
                <li><a href="#contact">Contact</a></li>
              </ul>
            </div><!--/.nav-collapse -->
          </div>
        </div>
    
        <!-- end navbar --> 
    
        <div class="container">
          <div class="row">
          </div>
        %(body)s
        
        <p style="font-size: smaller">
            <span style="font-style: italic">
                We hacked <a href="%(ABE_URL)s">%(APPNAME)s</a>.  A lot.  
            </span>
            
        </p>
    </body>
    </html>
    """
    return template
    

######SEARCH FORM WIDGET
def create_search_form():
    template ="""\
            <div class=\"row\">
              <div class=\"col-xs-8 col-xs-offset-2\">
                <h2>Search by wallet address, block ID, or transaction ID:</h2>
              </div>
            </div>
            <div class=\"row\">
              <div class=\"col-xs-8 col-xs-offset-2\">
                  <form action="../search">
                    <div class=\"input-group input-group-lg\">
                      <input name ="q" type=\"text\" class=\"form-control\" placeholder=\"Enter at least the first 6 characters\">
                      <span class=\"input-group-btn\">
                       <button class=\"btn btn-default\" type=\"submit\">Go!</button>
                      </span>          
                    </div>
                   </form>
              </div>
            </div>
    """
    return template
    
######SEARCH RESULTS
def show_search_results(error, results):
    print "R %s" % results
    template = create_search_form()
    template +="""\
            <div class=\"row\">
              <div class=\"col-xs-8 col-xs-offset-2\">
    """
    if error is not None:
        template += '<h2 class="error">Please enter search terms.</h2>'
    else:
        template +="""\
            <div class="panel panel-default">
                <div class="panel-heading">Search Results</div>
                    <table class="table">
        """
    for type in results:
        for result in results[type]:
            print "R %s" % result
            template += '<tr><td><a href="%s">%s</a></td></tr>' % (
                result['uri'], result ['name'])
            
    template +="""\
                </table>
    
            </div>
        </div>
        </div>
        </div>
    """
    
    return template
    
#####HOMEPAGE
#FIX ROW/COL
def generate_homepage(total_blocks, total_coins_created, cold_storage_wallets, show_search_form):
    template = ""
    if show_search_form == True:
        template += create_search_form()
    template += generate_summary_blocks_and_coins(total_blocks, total_coins_created, cold_storage_wallets)
    template += generate_cold_storage_table(cold_storage_wallets)
    return template

def generate_cold_storage_table(cold_storage_wallets):
  template = """\
  <div class="panel panel-default">
    <div class="panel-heading">Cold Storage</div>
      <table class="table">
        <tr><td>Wallet Address</td><td>Balance</td>
  """
  for wallet in cold_storage_wallets:
      template += "<tr><td>%s</td><td>§%s</td></tr>" % (wallet, cold_storage_wallets[wallet])
  
  template += """\
        </table>
     </div>
  </div>
  """
  return template

def generate_block_pager(basename, hi, count):
    #there's some corner cases that could use fixing, only an issue for coins with <count blocks
    first_link = '<a class="btn btn-lg btn-default" href="%s?hi=%s&count=%s">First</a>' % (basename, str(count), str(count))
    prev_link = '<a class="btn btn-lg btn-default" href="%s?hi=%s&count=%s">Previous</a>' % (basename, str(hi-count), str(count))
    current_link = '<a class="btn btn-lg active btn-default" href="#">%s-%s</a>' % (str(hi-count), str(hi))
    next_link = '<a class="btn btn-lg btn-default" href="%s?hi=%s&count=%s">Next</a>' % (basename, str(hi+count), str(count))
    latest_link = '<a class="btn btn-lg btn-default" href="%s?count=%s">Most Recent</a>' % (basename, str(count))
    
    pager = """\
    <div class="row">
      <div class="col-xs-6 col-xs-offset-3">
        <div class="btn-group">
          %s
          %s
          %s
          %s
          %s
        </div> 
      </div>
    </div>""" % (first_link, prev_link, current_link, next_link, latest_link)
    
    
    return pager
    
def generate_browse_blocks_page(block_dict, block_pager):
    template = ""
    template += block_pager
    template +="""\
      <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>All Blocks</h4></div>
            <table class="table">
              <tr>
                <td><h4>Block Number</h4></td>
                <td><h4>Creation Time</h4></td>
                <td><h4>Transactions</h4></td>
                <td><h4>Total SLR</h4></td>
              </tr>
    """
    
    for block in sorted(block_dict):
        template += "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"\
          % (block_dict[block]['link'], block_dict[block]['time'], block_dict[block]['num_tx'], block_dict[block]['value'])
    
    template +="""
            </table>
          </div>
        </div>
      </div>
      """
    
    template += block_pager
    return template
    
def generate_block_detail_page(block_details, next_list, tx_ids, txs):
    
    #prev/next
    prev_link = '<a class="btn btn-lg btn-default" href="../block/%s">Previous</a>' % block_details['prev_block_hash']
    current_link = '<a class="btn btn-lg active btn-default" href="#">Block # %s</a>' % block_details['block_number']
    next_link = ""
    for address in next_list:
        next_link += '<a class="btn btn-lg btn-default" href="%s">Next</a>' % address
    
    template = """\
    <div class="row">
      <div class="col-xs-4 col-xs-offset-4">
        <div class="btn-group center-block">
          %s
          %s
          %s
        </div> 
      </div>
    </div>""" % (prev_link, current_link, next_link)
    
    #block info
    template +="""\
      <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>Block Information</h4></div>
            <table class="table">
              <tr><td><h4>Block Number</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Creation Time</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Transactions</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Total SLR</h4></td><td><h4>§%s</h4></td></tr>
              
            </table>
          </div>
        </div>
      </div>""" % (block_details['block_number'], 
                   block_details['time'], 
                   block_details['num_transactions'],
                   block_details['value_out'])
    #transactions
    template +="""\
      <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>Transactions</h4></div>
            <table class="table">
              <tr>
                <td><h4>Transaction ID</h4></td>
                <td><h4>From (amount)</h4></td>
                <td><h4>To (amount)</h4></td>
              </tr>
    """
    for tx_id in tx_ids:
        tx = txs[tx_id]
        
        #transaction address
        template += '<tr><td><a href="../tx/%s">%s</a></td>' \
            % (tx['hash'], tx['hash'][:10])
        
        #from transactions
        template += '<td>'
        
        for from_dict in tx['display_in_transactions']:
            for from_address, amount in from_dict.items():
                template += "<div>%s (§%s)</div>" % (from_address, amount)
        template += '</td>'
        
        #to transactions
        template += '<td>'
        for to_dict in tx['display_out_transactions']:
            for to_address, amount in to_dict.items():
                template += "<div>%s (§%s)</div>" % (to_address, amount) 
        template += '</td>'
        
        
        
   
    
    template +="""        
            </table>
          </div>
        </div>
      </div>""" 
    
    #gross details
    template +="""\
      <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>Block Details</h4></div>
            <table class="table">
              <tr><td><h4>Nonce</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Merkle Root</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Difficulty</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Cumulative Difficulty</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Cumulative Coin-Days Destroyed</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Average Coin Age</h4></td><td><h4>%s days</h4></td></tr>
              <tr><td><h4>Version</h4></td><td><h4>%s</h4></td></tr>
            </table>
          </div>
        </div>
      </div>""" % (block_details['nonce'], 
                   block_details['merkle_root'], 
                   block_details['difficulty'],
                   block_details['cumulative_difficulty'],
                   block_details['cumulative_coin_dd'],
                   block_details['average_coin_age'],
                   block_details['version'])
              
    return template
    
        
def generate_transaction_detail_page(
    transaction_details, in_row_dict, out_row_dict):
        
    
    
    #create parent block string
    
    parent_block_label = ""
    parent_block_string = ""
    if len(transaction_details['in_blocks']) == 1:
        parent_block_label = "Parent Block:" 
        for block_addr in transaction_details['in_blocks'][0]:
            parent_block_string = '<a href="../block/%s">%s</a>' % (
                block_addr, block_addr)
    else:
        parent_block_label = "Parent Blocks:"
        for i in range(len(transaction_details['in_blocks'])):
            parent_block_string += '<a href="../block/%s">%s' %\
                (transaction_details['in_blocks'][i], 
                transaction_details['in_blocks'][i])
            if i == (len(transaction_details['in_blocks']) - 1):
                parent_block_string += "</a>"
            else:
                parent_block_string += "</a>, "
    
    
    
    #transaction info
    template ="""\
      <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>Transaction Information</h4></div>
            <table class="table">
              <tr><td><h4>Transaction Hash</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>%s</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Value In</h4></td><td><h4>§%s</h4></td></tr>
              <tr><td><h4>Value Out</h4></td><td><h4>§%s</h4></td></tr>
              <tr><td><h4>Fees</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Transaction Comment</h4></td><td><h4>%s</h4></td></tr>
              
              
            </table>
          </div>
        </div>
      </div>""" % (transaction_details['hash'],
                   parent_block_label,
                   parent_block_string,
                   transaction_details['total_value_in'],
                   transaction_details['total_value_out'],
                   transaction_details['fee'],
                   transaction_details['tx_comment'])
                   
                   
    template +="""\
      <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>Flows In</h4></div>
            <table class="table">
              <tr>
                <td><h4>Incoming Transaction</h4></td>
                <td><h4>From Address</h4></td>
                <td><h4>Amount</h4></td>
              </tr>
                """
    
    for tx in in_row_dict:
        
    #previous tx
        template += '<tr><td><a href="../tx/%s">%s</a></td>' \
            % ((tx['link_text']), tx['link_text'][:10])
        template += "<td>%s</td>" % tx['binaddr']
        template += "<td>§%s</td></tr>" % tx['amount']
    template += """
            </table>
          </div>
        </div>
      </div>"""
        
    template +="""\
      <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>Flows Out</h4></div>
            <table class="table">
              <tr>
                <td><h4>Outgoing Transaction</h4></td>
                <td><h4>To Address</h4></td>
                <td><h4>Amount</h4></td>
              </tr>
    """
    
    for tx in out_row_dict:
        
        #previous tx
        template += '<tr><td><a href="../tx/%s">%s</a></td>' \
            % ((tx['link_text']), tx['link_text'][:10])
        template += "<td>%s</td>" % tx['binaddr']
        template += "<td>§%s</td></tr>" % tx['amount']
    template += """
         </table>
          </div>
        </div>
      </div>"""
    
    return template
    
def generate_address_view(display_transactions):
    template ="""\
    <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>Address %s</h4></div>
            <table class="table">
              <tr><td><h4>Transactions in</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Transactions out</h4></td><td><h4>%s</h4></td></tr>
              <tr><td><h4>Received</h4></td><td><h4>§%s</h4></td></tr>
              <tr><td><h4>Sent</h4></td><td><h4>§%s</h4></td></tr>
              <tr><td><h4>Balance</h4></td><td><h4>§%s</h4></td></tr>
              
            </table>
          </div>
        </div>
      </div>""" % (display_transactions['address'],
                   display_transactions['transactions_in'], 
                   display_transactions['transactions_out'],
                   display_transactions['received'][0],
                   display_transactions['sent'][0],
                   display_transactions['balance'][0])
                   
    template +="""\
      <div class="row">
        <div class="col-xs-12">
          <div class="panel panel-default">
            <div class="panel-heading"><h4>Flows In</h4></div>
            <table class="table">
              <tr>
                <td><h4>Transaction</h4></td>
                <td><h4>Block</h4></td>
                <td><h4>Time</h4></td>
                <td><h4>Amount</h4></td>
              </tr>
                """
    
    for tx_dict in display_transactions['transaction_list']:
        
        template +="""\
        <tr>
          <td><a href="../tx/%s">%s</a></td>
          <td><a href="../block/%s">%s</a></td>
          <td>%s</td>
          <td>%s</td>
        </tr>""" % (tx_dict['tx_hash'],
                    tx_dict['tx_hash'],
                    tx_dict['block_hash'],
                    tx_dict['block_number'],
                    tx_dict['block_time'],
                    tx_dict['value'])
    
    template +="""\
            </table>
           </div>
         </div>
      </div>"""
    
    return template
                   
    
    
    
   
def generate_summary_blocks_and_coins(total_blocks, total_coins_created, cold_storage_wallets):
    template ="""\
    <div class="row">
      <div class="col-xs-4">
        <div class="panel panel-default">
          <div class="panel-heading"><h4>Total Blocks</h4></div>
          <div class="panel-body">{0}</div>
        </div>
      </div>

      <div class="col-xs-4">
        <div class="panel panel-default">
          <div class="panel-heading"><h4>Circulating Coins</h4></div>
          <div class="panel-body">§{1}</div>
        </div>
      </div>

      <div class="col-xs-4">
        <div class="panel panel-default">
          <div class="panel-heading"><h4>Total Coins Created</h4></div>
          <div class="panel-body">§{2}</div>
        </div>
      </div>
    </div>"""
    
    return template.format(total_blocks, float(total_coins_created)-float(cold_storage_wallets["Total"]), total_coins_created)
    
def get_nethash_svg_template():
    template = """\
    <?xml version="1.0" encoding="UTF-8" standalone="no"?>
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         xmlns:abe="http://abe.bit/abe"
         viewBox="0 0 1 100"
         preserveAspectRatio="none"
         onload="Abe.draw(this)">
    
      <style>
        #chart polyline { stroke-width: 0.1%%; fill-opacity: 0; }
      </style>
    
      <script type="application/ecmascript"
              xlink:href="%(dotdot)s%(STATIC_PATH)snethash.js"/>
    
      <g id="chart">
        <polyline abe:window="1d" style="stroke: red;"/>
        <polyline abe:window="3d" style="stroke: orange;"/>
        <polyline abe:window="7d" style="stroke: yellow;"/>
        <polyline abe:window="14d" style="stroke: green;"/>
        <polyline abe:window="30d" style="stroke: blue;"/>
    
    %(body)s
    
      </g>
    </svg>
    """
    return template
