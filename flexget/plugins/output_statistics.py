import sys
import os.path
import logging
from flexget.plugin import *

log = logging.getLogger('statistics')

has_sqlite = False
try:
    from pysqlite2 import dbapi2 as sqlite
    has_sqlite = True
except ImportError:
    try:
        from sqlite3 import dbapi2 as sqlite # try the 2.5+ stdlib
        has_sqlite = True
    except ImportError:
        raise Exception('Unable to use sqlite3 or pysqlite2', log)

try:
    from pygooglechart import StackedVerticalBarChart, Axis
except:
    print "Please run 'bin/paver clean' and then 'python bootstrap.py'"
    sys.exit(1)

class Statistics:
    """
        Saves statistics about downloaded releases and generates graphs from the data.
    
        Example:
        
        This will create the stats html in the specified location

        statistics:
            file: /home/user/public_html/flexget/index.html

        OR

        This example creates one stat file per config named 
        CONFIGNAME_statistics.html in flexget's root directory

        statistics: true
    """
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0

        self.written = False

    def validator(self):
        """Validate given configuration"""
        from flexget import validator
        root = validator.factory()
        root.accept('text')
        stats = root.accept('dict')
        stats.accept('text', key='file', required=True)
        return root

    def init(self, con):
        """Create the sqlite table if necessary"""
        
        create = """
        CREATE TABLE IF NOT EXISTS statistics
        (
           timestamp TIMESTAMP,
           feed varchar(255),
           success integer,
           failure integer
        );"""
        cur = con.cursor()
        cur.execute(create)
        con.commit()
        
    def on_feed_input(self, feed):
        self.total = len(feed.entries)

    def on_feed_exit(self, feed):
        self.passed = len(feed.accepted)
        self.failed = self.total - self.passed

        # don't bother to save the failed ones, the number is worth shit anyway
        #if not self.passed: return
        
        dbname = os.path.join(feed.manager.config_base, feed.manager.config_name+".db")
        con = sqlite.connect(dbname)
        self.init(con)
        cur = con.cursor()

        cur.execute("insert into statistics (timestamp, feed, success, failure) values (datetime('now'), ?, ?, ?);", (feed.name, self.passed, self.failed))

        con.commit()
        con.close()

    def get_config(self, feed):
        config = feed.config['statistics']
        if not isinstance(config, dict):
            config = {'file': os.path.join(feed.manager.config_base, feed.manager.config_name+'_statistics.html')}

        config['file'] = os.path.expanduser(config['file'])
        
        return config

    def on_process_end(self, feed):
        if feed._abort:
            return
        if self.written:
            log.debug("stats already done for this run")
            return

        log.debug("generating charts")
        self.written = True

        dbname = os.path.join(os.path.join(feed.manager.config_base, feed.manager.config_name+".db"))
        con = sqlite.connect(dbname)

        charts = []
        charts.append(self.weekly_stats_by_feed(con))
        charts.append(self.hourly_stats_by_feed(con))

        self.save_index(charts, feed)

    def save_index(self, charts, feed):
        imagelinks = ""
        for chart in charts:
            imagelinks += """<img src="%s" alt="" />""" % chart

        index = index_html % imagelinks

        config = self.get_config(feed)

        f = file(config['file'], 'w')
        f.write(index)
        f.close()

    def hourly_stats_by_feed(self, con):
        sql = """
        select feed, strftime("%H", timestamp, 'localtime') as hour, sum(success) from statistics group by feed, hour;
        """

        cur = con.cursor()
        cur.execute(sql)

        feedname = ""
        maxdata = 0
        values = []
        legend = []
        for feed, hour, success in cur:
            # clear data array for this feed
            if feed != feedname:
                feedname = feed
                legend.append(feedname)
                data = 24*[0]
                # add data set
                #chart.add_data(data)
                values.append(data)

            success = int(success)
            if success > maxdata:
                maxdata = success
            data[int(hour)] = success

        # 200 pixels hold exactly 11 feeds
        chartheight = 200
        if len(legend) > 11:
            chartheight = chartheight + ((len(legend)-11)*20)
        
        chart = StackedVerticalBarChart(800, chartheight, title="Releases by source")
        axislabels = [str(i) for i in range(24)]
            
        axis = chart.set_axis_labels(Axis.BOTTOM, axislabels)
        chart.set_axis_style(axis, '000000', alignment=-1)


        for value in values:
            chart.add_data(value)

        # random colors
        #import random as rn
        #colors = ["".join(["%02x" % rn.randrange(256) for x in range(3)]) for i in range(len(legend))]
        colors = ('00FFFF', '0000FF', 'FF00FF', '008000', '808080', '00FF00', '800000', '000080', '808000', '800080', 'FF0000', 'C0C0C0', '008080', 'FFFF00')
        chart.set_colours(colors)

        chart.set_axis_range(Axis.LEFT, 0, maxdata)
        chart.set_legend(legend)

        return chart.get_url()

    def weekly_stats_by_feed(self, con):
        sql = """
        select feed, strftime("%w", timestamp, 'localtime') as hour, sum(success) from statistics group by feed, hour;
        """

        cur = con.cursor()
        cur.execute(sql)

        feedname = ""
        maxdata = 0
        values = []
        legend = []
        for feed, dow, success in cur:
            dow = int(dow) - 1
            if dow == -1:
                dow = 6
            # clear data array for this feed
            if feed != feedname:
                feedname = feed
                legend.append(feedname)
                data = 7*[0]
                # add data set
                #chart.add_data(data)
                values.append(data)

            success = int(success)
            if success > maxdata:
                maxdata = success
            data[dow] = success

        # 200 pixels hold exactly 11 feeds
        chartheight = 200
        if len(legend) > 11:
            chartheight = chartheight + ((len(legend)-11)*20)

            
        chart = StackedVerticalBarChart(350, chartheight, title="Releases by source")
        axis = chart.set_axis_labels(Axis.BOTTOM, ['mon','tue','wed','thu','fri','sat','sun'])
        chart.set_axis_style(axis, '000000', alignment=-1)

        for value in values:
            chart.add_data(value)

        # random colors
        #import random as rn
        #colors = ["".join(["%02x" % rn.randrange(256) for x in range(3)]) for i in range(len(legend))]
        colors = ('00FFFF', '0000FF', 'FF00FF', '008000', '808080', '00FF00', '800000', '000080', '808000', '800080', 'FF0000', 'C0C0C0', '008080', 'FFFF00')
        chart.set_colours(colors)

        chart.set_axis_range(Axis.LEFT, 0, maxdata)
        chart.set_legend(legend)

        return chart.get_url()

register_plugin(Statistics, 'statistics')

index_html = """
<?xml version="1.0"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
<title>Flexget statistics</title>
  <link rel="stylesheet" type="text/css" href="http://yui.yahooapis.com/2.5.1/build/reset-fonts-grids/reset-fonts-grids.css" />
  <link rel="stylesheet" type="text/css" href="http://yui.yahooapis.com/2.5.1/build/base/base-min.css" />
</head>
<body class="yui-skin-sam">
<h1>Stats</h1>

<div id="charts">
%s
</div>

</body>
</html>
"""
