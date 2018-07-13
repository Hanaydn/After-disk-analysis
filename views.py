#coding:utf-8
import json
import os
from django.http import HttpResponse
from postts.values import DailyPositionsWithMd as dpmd
from postts.values import MarketData as md
from postts.values import OrdersPositions as op
from postts.values import DatesByProduct as dp
from postts.values import OpenClose as oc
from postts.values import CalQuotas as cq
from postts.values import DailyPnl as dpnl
 
def dates_by_product(request):
    return HttpResponse(json.dumps(dp.d_b_p()), content_type="application/json")
	
def orders_positions(request):
    date = request.GET['date']
    product = request.GET.get('product')
    return HttpResponse(json.dumps(op.o_p(date, product)), content_type="text/plain")
	
def market_data(request):
    date = request.GET['date']
    product = str(request.GET['product']).split('.')
    return HttpResponse(json.dumps(md.m_d(date, product[1], product[0])), content_type="text/plain")

def daily_positions_withmd(request):
    date = request.GET['date']
    product = request.GET['product']
    return HttpResponse(json.dumps(dpmd.d_p_m_d(date, product)), content_type="text/plain")
	
def open_close(request):
    date = request.GET['date']
    product = request.GET['product']
    open, close = oc.o_c(date, product)
	
    return HttpResponse(json.dumps({'open':open, 'close':close}), content_type="text/plain")
	
def read_static_pages(request):
    basedir = os.path.abspath('.') + '\\postts\\html'
    path = request.path.replace('/postts', basedir).replace('/', '\\')
    print(path)
    with open(path, 'r') as myfile:
        return HttpResponse(myfile.read())
	  
def cal_quotas(request):
    return HttpResponse(json.dumps(cq.c_q()), content_type="application/json")
	
def daily_pnl(request):
	date = str(request.GET['date']).split('-')
	infos, dates = dpnl.d_pnl(str(date[0]), str(date[1]))
	return HttpResponse(json.dumps({'infos':infos, 'dates':dates}), content_type="text/plain")
	
	
		
