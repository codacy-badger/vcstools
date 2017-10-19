#!/usr/bin/env python
import os, datetime, logging
import sqlite3 as lite
from optparse import OptionParser #NB zeus does not have argparse!

DB_FILE = os.environ['CMD_VCS_DB_FILE']

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d
    
def database_command(options, obsid):
        DB_FILE = os.environ['CMD_VCS_DB_FILE']
        opts_string = ""
        for a in options:
                if not a == options[0]:
                        opts_string = opts_string + str(a) + " "
                        
        con = lite.connect(DB_FILE)
        con.isolation_level = 'EXCLUSIVE'
        con.execute('BEGIN EXCLUSIVE')
        with con:
                cur = con.cursor()
                
                cur.execute("INSERT INTO ProcessVCS(Arguments, Obsid, UserId, Started) VALUES(?, ?, ?, ?)", (opts_string, obsid, os.environ['USER'], datetime.datetime.now()))
                vcs_command_id = cur.lastrowid
        return vcs_command_id
    
def add_database_function():
    batch_line ='function run\n' +\
                '{\n' +\
                '    # run command and add relevant data to the job database\n' +\
                '    # 1st parameter is command to be run including aprun (e.g. wsclean)\n' +\
                '    # 2nd parameter is parameters to that command (e.g. "-j $ncpus")\n' +\
                '    # 3rd parameter is vcs row number\n' +\
                '    command="${1##*/}"\n' +\
                '    command="${command##* }"\n' +\
                '    rownum=`database_vcs.py -m "s" -v "$3" -c "$command" -a "$2"`\n' +\
                '    $1 $2\n' +\
                '    errcode=$?\n' +\
                '    database_vcs.py -m "e" -r $rownum --errorcode $errcode\n' +\
                '    echo "database_vcs.py -m "e" -r $rownum --errorcode $errcode"\n' +\
                '    if [ "$errcode" != "0" ]; then\n' +\
                '        return $errcode\n' +\
                '    fi\n' +\
                '}\n'
    return batch_line
    
    
def database_script_start(vcs_id, command, arguments):
    import datetime
    con = lite.connect(DB_FILE)
    with con:
        cur = con.cursor()
        cur.execute("INSERT INTO Commands (trackvcs, Command, Arguments, Started) VALUES(?, ?, ?, ?)", (vcs_id, command, arguments, datetime.datetime.now()))
        row_id = cur.lastrowid
    return row_id

def database_script_stop(rownum, errorcode):    
    end_time = datetime.datetime.now()

    con = lite.connect(DB_FILE)
    with con:
        cur = con.cursor()
        cur.execute("SELECT Ended FROM Commands WHERE Rownum=?", (rownum,))
        ended = cur.fetchone()[0]
        if ended is not None:
            logging.warn("Overwriting existing completion time: %s" % ended)
        cur.execute("UPDATE Commands SET Ended=?, Exit=? WHERE Rownum=?", (end_time, errorcode, rownum))


if __name__ == '__main__':
    from optparse import OptionParser, OptionGroup, SUPPRESS_HELP
    parser = OptionParser(usage = "usage: %prog <options>" +
    """
    Script used to manage the VCS database by recording the scripts process_vcs.py uses and prints the databse
    """)
    parser.add_option("-m", "--mode", dest="mode", metavar="mode", default='v', type=str, help='This script has three modes: "vc" used to view the database commands, "vs" used to view the database scripts,, "s" used to start a record of a script on the database and "e" used to record the end time and error code of a script on the database. Default mode is v')
    
    view_options = OptionGroup(parser, 'View Options')
    view_options.add_option("--recent", dest="recent", metavar="HOURS", default=None, type=float, help="print only jobs started in the last N hours")
    view_options.add_option("-n", "--number", dest="n", metavar="N", default=20, type=int, help="number of jobs to print [default=%default]")
    view_options.add_option("--all", dest="all", action="store_true", help="print all lines of the database")
    view_options.add_option("-s", "--startrow", dest="startrow", default=0, type=int, help="ignore any row earlier than this one")
    view_options.add_option("-e", "--endrow", dest="endrow", default=None, type=int, help="ignore any row later than this one")
    view_options.add_option("-u", "--user", dest="user", default=None, type=str, help="Only prints one user's jobs.")
    view_options.add_option("-o", "--obsid", dest="obsid", default=None, type=str, help="Only prints one obsid's jobs.")
    
    start_options = OptionGroup(parser, 'Script Start Options')
    start_options.add_option("-v", "--vcs_id", dest="vcs_id", default=None, type=str, help="The row number of the process vcs command of the databse")
    start_options.add_option("-c", "--command", dest="command", default=None, type=str, help="The script name being run. eg volt_download.py.")
    start_options.add_option("-a", "--argument", dest="argument", default=None, type=str, help="The arguments that script used.")
    
    end_options = OptionGroup(parser, 'Script End Options')
    end_options.add_option("--errorcode", dest="errorcode", default=None, type=str, help="Error code of scripts.")
    end_options.add_option("-r", "--rownum", dest="rownum", default=None, type=str, help="The row number of the script.")
    parser.add_option_group(view_options)
    parser.add_option_group(start_options)
    parser.add_option_group(end_options)
    (opts, args) = parser.parse_args()
    
    
    
    if opts.mode == "s":
        vcs_row = database_script_start(opts.vcs_id, opts.command, opts.argument)
        print vcs_row
    elif opts.mode == "e":
        database_script_stop(opts.rownum, opts.errorcode)
    elif opts.mode == "vc" or opts.mode == "vs":
        con = lite.connect(DB_FILE)
        con.row_factory = dict_factory
    
        if opts.mode == "vc":
            query = "SELECT * FROM ProcessVCS"
        if opts.mode == "vs":
            query = "SELECT * FROM Commands"
            
        if opts.user:
            query += " WHERE UserId='" + str(opts.user) + "'"

        if opts.obsid:
            query += " WHERE Arguments LIKE '%" + str(opts.obsid) + "%'"

        if opts.recent is not None:
            query += ''' WHERE Started > "%s"''' % str(datetime.datetime.now() - relativedelta(hours=opts.recent))
            logging.debug(query)
        if opts.vcs_id:
            query += " WHERE trackvcs='" + str(opts.vcs_id) + "'"

        with con:
            cur = con.cursor()
            cur.execute(query)
            rows = cur.fetchall()

        if opts.startrow or opts.endrow:
            rows = rows[opts.startrow:]
            if opts.endrow is not None:
                rows = rows[:opts.endrow+1]
        elif not (opts.all or opts.recent):
            rows = rows[-opts.n:]
        
        
        if opts.mode == "vc": 
            print 'Row# ','Obsid       ','Started               ','UserID       ','Arguments'
            print '--------------------------------------------------------------------------------------------------'

            for row in rows:
                if not ( (row['Rownum'] is None) or (row['Obsid'] is None) or (row['Started'] is None) or\
                         (row['UserId'] is None) or (row['Arguments'] is None) ):
                    print '%-5s' % (str(row['Rownum']).rjust(4)),
                    print '%-12s' % (row['Obsid']),
                    print '%-22s' % (row['Started'][:19]),
                    print '%-13s' % (row['UserId'].ljust(10)),
                    print row['Arguments']
                    print "\n"
        if opts.mode == "vs":
            print 'VCS# ','Command             ','Started               ','Ended                 ','Exit_Code','Arguments'
            print '--------------------------------------------------------------------------------------------------'

            for row in rows:
                if not ( (row['trackvcs'] is None) or (row['Command'] is None) or\
                         (row['Started'] is None) or (row['Ended'] is None) or\
                         (row['Exit'] is None) or (row['Arguments'] is None) ):
                    print '%-5s' % (str(row['trackvcs']).rjust(4)),
                    print '%-20s' % (row['Command']),
                    print '%-22s' % (row['Started'][:19]),
                    if row['Ended'] is None:
                        print '%-22s' % (row['Ended']),
                    else:
                        print '%-22s' % (row['Ended'][:19]),
                    print '%-5s' % (row['Exit']),
                    print row['Arguments'],
                    print "\n"
