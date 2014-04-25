def get_default_template(dotdot, title): 
  template = """
	<!DOCTYPE html>
	<html lang="en">
	<head>
		<link rel="stylesheet" type="text/css"
		 href="%(dotdot)s%(STATIC_PATH)sabe.css" />
		<link rel="shortcut icon" href="%(dotdot)s%(STATIC_PATH)sfavicon.ico" />
		<link rel="stylesheet" href="//netdna.bootstrapcdn.com/bootstrap/3.1.1/css/bootstrap.min.css">
		<title>%(title)s</title>
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
				<li class="active"><a href="#">Home</a></li>
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
		<p><a href="%(dotdot)sq">API</a> (machine-readable pages)</p>
		<p style="font-size: smaller">
			<span style="font-style: italic">
				Powered by <a href="%(ABE_URL)s">%(APPNAME)s</a>
			</span>
			%(download)s
			Tips appreciated!
			<a href="%(dotdot)saddress/%(DONATIONS_BTC)s">BTC</a>
			<a href="%(dotdot)saddress/%(DONATIONS_NMC)s">NMC</a>
		</p>
	</body>
	</html>
	"""
  return template
