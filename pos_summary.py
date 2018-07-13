import sys, json, traceback
import mysql.connector as mariadb
import time, datetime
from md_lib import *

def lp_c(prod, date):
  try:
    return ["", ""]
    if date == "" or prod == "": return ['', '']
    prod, exch = prod.strip().split('.')
    base_dir = "/mnt/SIPMarketData/extracted/{0}/{1}/{2}.csv"
    
    fpath = base_dir.format(date, exch, prod)
    with open(fpath, 'r') as f:
      dat = f.readlines()[-1].strip().split(',')
      pre_close, last_price, high, low = float(dat[3]), float(dat[7]) / 1e4, float(dat[5]), float(dat[6])
    return [str(last_price), "{:.3f}%".format((high - low)/pre_close * 100)]
  except:
    return ['', '']

def fmt(v):
  try:
    nv = int(float(v))
    return str(nv) if nv - v == 0 else str(v)
  except:
    return str(v)

class DBConn(object):
  def __init__(self, sdate, edate, args={}):
    self.conn = mariadb.connect(user='root', password='hramc-123', host='192.168.1.121', database='trading_system')
    self.cursor = self.conn.cursor()
    self.sdate, self.edate, self.args = sdate, edate, args
  def exec(self, sql_t, *args):
    sql = sql_t.format(*args, sdate=self.sdate, edate=self.edate, **self.args)
    self.cursor.execute(sql)
  def q_2_csv(self, sql_t, *args):
    self.exec(sql_t, *args)
    return '\n'.join(','.join([fmt(v) if v is not None else '' for v in row]) for row in self.cursor)
  def close(self):
    self.conn.close()

  def get_all_date(self):
    self.cursor.execute("select distinct date(otime) from PositionReports")
    return [date[0].strftime('%Y%m%d') for date in self.cursor.fetchall()]

  def get_all_product(self):
    self.cursor.execute("select '' as product union select distinct product from PositionReports order by product")
    # product_list = []
    # for product in self.cursor.fetchall():
    #     product_list.append(product[0])
    return [product[0] for product in self.cursor.fetchall()]

  def get_all_account(self):
    return sorted(['FOF6','FOF7','MarginAccount','MA15','DCL2','', 'SZ1'])

  def get_daily_profit(self):
    get_daily_profit_sql = """
       select product, date(otime) as dt, round(filled_close_qty * unit_profit,2) as daily_profit
       from PositionReports where class='TFS' and filled_close_qty is not null group by product, dt having dt between '{sdate}' and '{edate}'"""
    self.cursor.execute(get_daily_profit_sql.format(get_daily_profit_sql, sdate=self.sdate, edate=self.edate, **args))
    # {"infos": {PRODUCT1: {DATE1: PROFIT1, DATE2: PROFIT2, ...},
    #             PRODUCT2: {DATE1: PROFIT1, DATE2: PROFIT2, ...}},
    #  "dates": {DATE1: INDEX1, DATE2: INDEX2}}
    infos, dates = {}, set()
    for row in self.cursor.fetchall():
      product, date, profit = row[0], row[1].strftime('%Y%m%d'), row[2]
      if product not in infos:
        infos[product] = {}
      infos[product][date] = profit
      dates.add(date)
    dates = sorted(list(dates))
    return {"infos": infos, "dates": dict(zip(dates, range(1, len(dates) + 1)))}

  def o_c(self, date, product):
    cursor = self.cursor
    sql = '''SELECT UNIX_TIMESTAMP(o.ctime), p.side AS ps, o.side AS os, o.price FROM trading_system.Positions p, trading_system.Orders o 
  WHERE o.pid = p.id AND date(o.ctime) = \'%(date)s\' AND product = \'%(product)s\';''' % {'date':date, 'product':product}
    cursor.execute(sql)
    results = cursor.fetchall()
    open = []
    close = []
    for row in results:
      if row[1] == row[2]:
        open.append([int(row[0])*1000, row[3]])
      else:
        close.append([int(row[0])*1000, row[3]])
    return open, close

  def o_p(self, date, product = ''):
    cursor = self.cursor
    sql = '''SELECT p.id AS pid, p.side AS ps, p.product, o.id AS oid, 
    o.side AS os, UNIX_TIMESTAMP(o.ctime), o.price, o.qty, o.cum_qty, o.avg_price, o.status 
    FROM trading_system.Positions p, trading_system.Orders o 
    WHERE o.pid = p.id AND date(o.ctime) = \'%(date)s\'''' % {'date':date}
    
    if product:
      sql = sql + ' AND product = \'' + product + '\''
    
    cursor.execute(sql)
    results = cursor.fetchall()
    
    positions = {}
    for row in results:
      if row[0] in positions.keys():
        positions[row[0]]['orders'][row[3]] = {'side':row[4], 'ctime':int(row[5])*1000, 'price':row[6], 'qty':row[7], 'cum_qty':row[8], 'avg_price':row[9], 'status':row[10]}
      else:
        positions[row[0]] = {'dir':row[1], 'prod':row[2], 'orders':{row[3]:{'side':row[4], 'ctime':int(row[5])*1000, 'price':row[6], 'qty':row[7], 'cum_qty':row[8], 'avg_price':row[9], 'status':row[10]}}};
    return positions

  def get_pos_detail(self):
    product = self.args['product']
    p = product.split('.')
    mds = get_md(self.sdate, p[1], p[0])
    positions = self.o_p(self.sdate, product)
    open, close = self.o_c(self.sdate, product)
    return {'mds': mds, 'positions':positions, 'open':open, 'close':close}

def setup_dargs(args):
  dargs = {"product": "", "account": ("" if "account" not in args else "Connection={0};".format(args["account"])), "stime": "00:00:00", "etime": "11:59:59"}
  dargs.update(args)
  return dargs

def sum_by_prod(sdate, edate, args):
  args = setup_dargs(args)
  sum_by_prod_sql = """
select r.product, date(otime),
  sum(filled_open_qty) topen_qty, sum(filled_close_qty) tclose_qty,
  round(sum(if(r.side='b', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tbuy,
  round(sum(if(r.side='s', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tsell,
  round(sum(unit_profit * filled_close_qty), 2) profit,
  round(sum(open_comm + close_comm), 2) comm,
  concat(format(sum(unit_profit * filled_close_qty) * 2 / sum((avg_fill_open + avg_fill_close)*filled_close_qty)*100, 3), '%') profit_ratio, count(*) ttrade,
  concat(format(sum(if(unit_profit > 0, 1, 0)) / sum(if(filled_close_qty > 0, 1, 0)) * 100, 3), '%')  winratio
from PositionReports r, Positions p where class='TFS' and p.id = r.id and p.side like '%{0}%' and p.attributes like '%{account}%'
and date(otime) between '{sdate}' and '{edate}' group by product"""
  conn, empty, data =  DBConn(sdate, edate, args), ',,,,,,,,', {}
  cursor = conn.cursor

  cursor.execute(sum_by_prod_sql.format('', sdate=sdate, edate=edate, **args))
  def to_str(row):
    return ','.join([fmt(v) if v is not None else '' for v in row[2:]])
  for row in cursor: data[row[0]] = [to_str(row), empty, empty]
  cursor.execute(sum_by_prod_sql.format('b', sdate=sdate, edate=edate, **args))
  for row in cursor: data[row[0]][1] = to_str(row)
  cursor.execute(sum_by_prod_sql.format('s', sdate=sdate, edate=edate, **args))
  for row in cursor: data[row[0]][2] = to_str(row)
  return '\n'.join(','.join([str(v) for v in [k] + data[k]]) for k in sorted(data.keys(), reverse=True))

def gen_data(sdate, edate, args):
  args = setup_dargs(args)

  all_sum_sql = """
select r.product, date(otime),
  sum(filled_open_qty) topen_qty, sum(filled_close_qty) tclose_qty,
  round(sum(if(r.side='b', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tbuy,
  round(sum(if(r.side='s', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tsell,
  round(sum(unit_profit * filled_close_qty), 2) profit,
  round(sum(open_comm + close_comm), 2) comm,
  concat(format(sum(unit_profit * filled_close_qty) * 2 / sum((avg_fill_open + avg_fill_close)*filled_close_qty)*100, 3), '%') profit_ratio, count(*) ttrade,
  concat(format(sum(if(unit_profit > 0, 1, 0)) / sum(if(filled_close_qty > 0, 1, 0)) * 100, 3), '%')  winratio
from PositionReports r, Positions p where class='TFS' and p.id = r.id and p.product like '%{product}%' and p.attributes like '%{account}%'
and date(otime) between '{sdate}' and '{edate}' group by product, date(otime)
union
select "", "",
  sum(filled_open_qty) topen_qty, sum(filled_close_qty) tclose_qty,
  round(sum(if(r.side='b', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tbuy,
  round(sum(if(r.side='s', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tsell,
  round(sum(unit_profit * filled_close_qty), 2) profit,
  round(sum(open_comm + close_comm), 2) comm,
  concat(format(sum(unit_profit * filled_close_qty) * 2 / sum((avg_fill_open + avg_fill_close)*filled_close_qty)*100, 3), '%') profit_ratio, count(*) ttrade,
  concat(format(sum(if(unit_profit > 0, 1, 0)) / sum(if(filled_close_qty > 0, 1, 0)) * 100, 3), '%')  winratio
from PositionReports r, Positions p where class='TFS' and p.id = r.id and p.product like '%{product}%' and p.attributes like '%{account}%'
and date(otime) between '{sdate}' and '{edate}'"""

  sum_by_dir_sql = """
select r.product, date(otime),
  sum(filled_open_qty) topen_qty, sum(filled_close_qty) tclose_qty,
  round(sum(if(r.side='b', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tbuy,
  round(sum(if(r.side='s', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tsell,
  round(sum(unit_profit * filled_close_qty), 2) profit,
  round(sum(open_comm + close_comm), 2) comm,
  concat(format(sum(unit_profit * filled_close_qty) * 2 / sum((avg_fill_open + avg_fill_close)*filled_close_qty)*100, 3), '%') profit_ratio, count(*) ttrade,
  concat(format(sum(if(unit_profit > 0, 1, 0)) / sum(if(filled_close_qty > 0, 1, 0)) * 100, 3), '%')  winratio
from PositionReports r, Positions p where class='TFS' and r.id = p.id and p.product like '%{product}%' and p.attributes like '%{account}%'
and r.side = '{0}' and date(otime) between '{sdate}' and '{edate}' group by product, date(otime)
union
select "", "",
  sum(filled_open_qty) topen_qty, sum(filled_close_qty) tclose_qty,
  round(sum(if(r.side='b', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tbuy,
  round(sum(if(r.side='s', avg_fill_open * filled_open_qty, avg_fill_close * filled_close_qty)), 2) tsell,
  round(sum(unit_profit * filled_close_qty), 2) profit,
  round(sum(open_comm + close_comm), 2) comm,
  concat(format(sum(unit_profit * filled_close_qty) * 2 / sum((avg_fill_open + avg_fill_close)*filled_close_qty)*100, 3), '%') profit_ratio, count(*) ttrade,
  concat(format(sum(if(unit_profit > 0, 1, 0)) / sum(if(filled_close_qty > 0, 1, 0)) * 100, 3), '%')  winratio
from PositionReports r, Positions p where class='TFS' and p.id = r.id and p.product like '%{product}%' and p.attributes like '%{account}%'
and r.side = '{0}' and date(otime) between '{sdate}' and '{edate}' """

  all_pos_sql = """
select r.param, r.product, r.id,
  filled_open_qty - ifnull(filled_close_qty, 0) lvs,
  r.otime, open_qty, round(avg_open, 2) avg_open, filled_open_qty, round(avg_fill_open, 2) avg_fill_open, round(open_comm, 2) open_comm,
  r.ctime, close_qty, round(avg_close, 2) avg_close, filled_close_qty, round(avg_fill_close, 2) avg_fill_close, round(close_comm, 2) close_comm,
  round(unit_profit * filled_close_qty, 2) profit
from PositionReports r, Positions p where p.side='{0}' and class='TFS' and r.id = p.id and p.product like '%{product}%' and p.attributes like '%{account}%'
and date(otime) between '{sdate}' and '{edate}'"""

  all_ords_sql = """
select o.pid, o.id, p.product, 
  if(p.side = 'b', 'long', 'short') dir, o.side, o.ctime, o.price, round(o.avg_price, 2) avg_price, o.qty, o.cum_qty, o.status
from Orders o, Positions p, Portfolios pt
where pt.class='TFS' and p.product like '%{product}%' and p.attributes like '%{account}%'
and o.pid = p.id and p.pid = pt.id and date(p.ctime) between '{sdate}' and '{edate}'"""

  lvs_rpt_sql = """
select r.id, r.product, if(r.side = 'b', 'long', 'short') dir,
  filled_open_qty, round(avg_fill_open, 2), 
  filled_open_qty - ifnull(filled_close_qty, 0) as lvs
from PositionReports r, Positions p where class='TFS' and p.product like '%{product}%' and p.attributes like '%{account}%'
and r.id = p.id and filled_open_qty - ifnull(filled_close_qty, 0) != 0 and date(otime) between '{sdate}' and '{edate}'"""
  
  conn, empty, data =  DBConn(sdate, edate, args), ',,,,,,,,', {}
  cursor = conn.cursor

  cursor.execute(all_sum_sql.format(sdate=sdate, edate=edate, **args))
  def to_str(row):
    return ','.join([fmt(v) if v is not None else '' for v in row[2:]])
  def key(row):
    return (row[0], row[1]) if "order_by_prod" in args else (row[1], row[0])
  for row in cursor:
    date = row[1].replace('-', '')
    data[key(row)] = lp_c(row[0], date) + [to_str(row), empty, empty]
  cursor.execute(sum_by_dir_sql.format('b', sdate=sdate, edate=edate, **args))
  for row in cursor:
    data[key(row)][3] = to_str(row)
  cursor.execute(sum_by_dir_sql.format('s', sdate=sdate, edate=edate, **args))
  for row in cursor:
    data[key(row)][4] = to_str(row)

  result = {"summary": '\n'.join(','.join([str(v) for v in list(k) + data[k]]) for k in sorted(data.keys(), reverse=True)),
            "long":"", "short":"", "leaves":"", "orders":""}
  if "all" in args:
    result.update({"long": conn.q_2_csv(all_pos_sql, 'b'), "short": conn.q_2_csv(all_pos_sql, 's'),
            "leaves": conn.q_2_csv(lvs_rpt_sql), "orders": conn.q_2_csv(all_ords_sql)})

  conn.close()
  return result

def profit_sum(sdate, edate, args):
  args = setup_dargs(args)
  ps_sql = """
select unix_timestamp(cdate) * 1000, round(profit, 2) profit, round(@cum_profit := @cum_profit + profit, 2) as cum_profit, total
from (select date(otime) cdate,
  round(sum(filled_close_qty * avg_fill_open), 2) total,
  sum(unit_profit * filled_close_qty)  profit
from PositionReports r, Positions p where filled_close_qty > 0 and r.id = p.id and r.class='TFS'
  and time(otime) between '{stime}' and '{etime}'
  and p.product like '%{product}%' and p.attributes like '%{account}%' and p.side like '%{0}%'
group by cdate having cdate between '{sdate}' and '{edate}') as t order by cdate"""
  ps_sql_by_prod = """
select unix_timestamp(cdate) * 1000, product, round(profit, 2) profit, round(@cum_profit := @cum_profit + profit, 2) as cum_profit, total
from (select date(otime) cdate, product,
  round(sum(filled_close_qty * avg_fill_open), 2) total,
  sum(unit_profit * filled_close_qty)  profit
from PositionReports r, Positions p where filled_close_qty > 0 and r.id = p.id and
  r.class='TFS' and p.product like '%{product}%' and p.attributes like '%{account}%'
group by cdate, product having cdate between '{sdate}' and '{edate}') as t order by cdate"""

  conn =  DBConn(sdate, edate, args)

  def qry(side):
    conn.cursor.execute('set @cum_profit := 0')
    conn.exec(ps_sql, side)
    return [[int(r[0]), float(r[1]), float(r[2]), float(r[3])] for r in conn.cursor]
  return {"total": qry(""), "long": qry("b"), "short": qry("s")}

def get_all_date(sdate, edate, args):
  args = setup_dargs(args)
  conn =  DBConn(sdate, edate, args)
  return conn.get_all_date()

def get_all_product(sdate, edate, args):
  args = setup_dargs(args)
  conn =  DBConn(sdate, edate, args)
  return conn.get_all_product()

def get_all_account(sdate, edate, args):
  args = setup_dargs(args)
  conn =  DBConn(sdate, edate, args)
  return conn.get_all_account()

def get_daily_profit(sdate, edate, args):
  args = setup_dargs(args)
  conn =  DBConn(sdate, edate, args)
  return conn.get_daily_profit()

def get_pos_detail(sdate, edate, args):
  args = setup_dargs(args)
  conn =  DBConn(sdate, edate, args)
  return conn.get_pos_detail()

def seg_by_tm(sdate, edate, args):
  args = setup_dargs(args)
  seg_by_tm_sql ="""
select product,
 sum(if(time_index = 0, profit, null)) as `T0930_1000`,
 sum(if(time_index = 1, profit, null)) as `T1000_1030`,
 sum(if(time_index = 2, profit, null)) as `T1030_1100`,
 sum(if(time_index = 3, profit, null)) as `T1100_1130`,
 sum(if(time_index = 4, profit, null)) as `T1300_1330`,
 sum(if(time_index = 5, profit, null)) as `T1330_1400`,
 sum(if(time_index = 6, profit, null)) as `T1400_1430`,
 sum(if(time_index = 7, profit, null)) as `T1430_1500`,
 sum(profit) as total
from( select  r.product, max(time(otime)) max_otime, 
sum(unit_profit * filled_close_qty) profit, count(*) total_trade, sum(if(unit_profit > 0, 1, 0)) win, 
sum(if(unit_profit <= 0, 1, 0)) lose, if(time(otime) <= time('11:30:00'),
floor(time_to_sec(timediff(time(otime), time('09:30:00'))) / (30*60)),
floor(time_to_sec(timediff(time(otime), time('13:00:00'))) / (30*60)) + 4) time_index
from PositionReports r, Positions p where r.product like '%{product}%' and r.side like '%{0}%' and p.attributes like '%{account}%' and 
date(r.otime) between '{sdate}' and '{edate}' and r.id = p.id and unit_profit is not null
group by time_index, product order by product, time_index) as t group by product"""
  conn =  DBConn(sdate, edate, args)
  return conn.q_2_csv(seg_by_tm_sql, '')

def parse_arg():
  return {} if len(sys.argv) == 1 else \
    {v[0]: v[1] for v in [i.split('=') for i in sys.argv[1].split(';') if i != ""]}

def get_date(args):
  if args.get('date', "").strip() == "":
    return '', ''
  dates = args['date'].split('-')
  if len(dates) == 1: return dates[0], dates[0]
  return dates[0], dates[1]

if __name__ == "__main__":
  args = parse_arg()
  sdate, edate = get_date(args)
  code = "all" if "code" not in args else args["code"]
  functions = {"all": gen_data, "profit_sum": profit_sum, "sum_by_prod": sum_by_prod, 
    "seg_by_tm": seg_by_tm,"get_all_date":get_all_date,"get_all_product":get_all_product,
    "get_all_account":get_all_account,"get_daily_profit":get_daily_profit,"get_pos_detail":get_pos_detail}
  try:
    if code in functions:
      print(json.dumps(functions[code](sdate, edate, args)))
  except: 
    traceback.print_exc(file=sys.stdout)
