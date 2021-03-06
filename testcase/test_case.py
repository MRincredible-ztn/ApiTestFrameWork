#!/user/bin/env python
#coding=utf-8
'''
@project : my_rf
@author  : djcps
#@file   : testcase.py
#@ide    : PyCharm
#@time   : 2019-05-28 12:37:01
'''

import unittest
from ddt import *
from core.readExcel import *
from core.testBase import *
import jsonpath
from core.functions import *
from db_operate.mysql_operate import MySQLOperate
from db_operate.redis_operate import RedisOperate



@ddt
class Test(unittest.TestCase):

    excel_data = read_excel()

    # 全局变量池
    saves = {}
    # 识别${key}的正则表达式
    EXPR = '\$\{(.*?)\}'
    # 识别函数助手
    FUNC_EXPR = '__.*?\(.*?\)'

    def save_date(self,source,key,jexpr:str):
        '''
        提取参数并保存至全局变量池
        :param source: 目标字符串
        :param key: 全局变量池的key
        :param jexpr: jsonpath表达式
        :return:
        '''
        if jexpr.startswith("$"):
            value = jsonpath.jsonpath(source,jexpr)
            if not value:
                raise KeyError("该jsonpath未匹配到值,请确认接口响应和jsonpath正确性")
            value = value[0]
            self.saves[key] = value
            logger.info("保存 {}=>{} 到全局变量池".format(key,value))
        else:
            self.saves[key] = jexpr
            logger.info("保存 {}=>{} 到全局变量池".format(key, jexpr))

    def build_param(self,s,id):
        '''
        识别${key}并替换成全局变量池的value,处理__func()函数助手
        :param s: 待替换的字符串
        :return:
        '''

        #遍历所有取值并做替换
        keys = re.findall(self.EXPR, s)
        for key in keys:
            value = self.saves.get(key+"-"+id)
            s = s.replace('${'+key+'}',str(value))


        #遍历所有函数助手并执行，结束后替换
        funcs = re.findall(self.FUNC_EXPR, s)
        for func in funcs:
            fuc = func.split('__')[1]
            fuc_name = fuc.split("(")[0]
            fuc = fuc.replace(fuc_name,fuc_name.lower())
            value = eval(fuc)
            s = s.replace(func,str(value))
        return s

    def execute_setup_sql(self,db_connect,setup_sql):
        '''
        执行setup_sql,并保存结果至参数池
        :param db_connect: mysql数据库实例
        :param setup_sql: 前置sql
        :return:
        '''
        for sql in [i for i in setup_sql.split(";") if i != ""]:
            result = db_connect.execute_sql(sql)
            logger.info("执行前置sql====>{}，影响条数:{}".format(sql,result))
            if sql.lower().startswith("select"):
                logger.info("执行前置sql====>{}，获得以下结果集:{}".format(sql,result))
                # 获取所有查询字段，并保存至公共参数池
                for key in result.keys():
                    self.saves[key] = result[key]
                    logger.info("保存 {}=>{} 到全局变量池".format(key, result[key]))

    def execute_teardown_sql(self,db_connect,teardown_sql):
        '''
        执行teardown_sql,并保存结果至参数池
        :param db_connect: mysql数据库实例
        :param teardown_sql: 后置sql
        :return:
        '''
        for sql in [i for i in teardown_sql.split(";") if i != ""]:
            result = db_connect.execute_sql(sql)
            logger.info("执行后置sql====>{}，影响条数:{}".format(sql, result))
            if sql.lower().startswith("select"):
                logger.info("执行后置sql====>{}，获得以下结果集:{}".format(sql, result))
                # 获取所有查询字段，并保存至公共参数池
                for key in result.keys():
                    self.saves[key] = result[key]
                    logger.info("保存 {}=>{} 到全局变量池".format(key, result[key]))

    def execute_redis_get(self,redis_connect,keys):
        '''
        读取redis中key值,并保存结果至参数池
        :param redis_connect: redis实例
        :param keys:
        :return:
        '''
        for key in [key for key in keys.split(";") if key!=""]:
            value = redis_connect.get(key)
            self.saves[key] = value
            logger.info("保存 {}=>{} 到全局变量池".format(key, value))


    @classmethod
    def setUpClass(cls):
        # 实例化测试基类，自带cookie保持
        cls.request = BaseTest()


    for sheet_data in excel_data:

        sheet = sheet_data.get("sheet")
        sdata = sheet_data.get("data")
        id = uuid()
        exec(F'''
@data(*{sdata})
@unpack
def test_{sheet}(self,descrption,url,method,headers,cookies,params,body,file,verify,saves,
                                                                            dbtype,db,setup_sql,teardown_sql):
          
    logger.info("用例描述====>"+descrption)
    
    url = self.build_param(url,"{id}")
    headers = self.build_param(headers,"{id}")
    params = self.build_param(params,"{id}")
    body = self.build_param(body,"{id}")
    setup_sql = self.build_param(setup_sql,"{id}")
    teardown_sql = self.build_param(teardown_sql,"{id}")

    params = eval(params) if params else params
    headers = eval(headers) if headers else headers
    cookies = eval(cookies) if cookies else cookies
    body = eval(body) if body else body
    file = eval(file) if file else file

    db_connect = None
    redis_db_connect = None
    res = None
    # 判断数据库类型,暂时只有mysql,redis
    if dbtype.lower() == "mysql":
        db_connect = MySQLOperate(db)
    elif dbtype.lower() == "redis":
        redis_db_connect = RedisOperate(db)
    else:
        pass

    if db_connect:
        self.execute_setup_sql(db_connect,setup_sql)
    if redis_db_connect:
        # 执行teardown_redis操作
        self.execute_redis_get(redis_db_connect,setup_sql)

    # 判断接口请求类型
    if method.upper() == 'GET':
        res = self.request.get_request(url=url,params=params,headers=headers,cookies=cookies)
    elif method.upper() == 'POST':
        res = self.request.post_request(url=url,headers=headers,cookies=cookies,params=params,json=body)
    elif method.upper() == 'UPLOAD':
        res = self.request.upload_request(url=url,headers=headers,cookies=cookies,params=params,data=body,files=file)
    elif method.upper() == 'PUT':
        res = self.request.put_request(url=url,headers=headers,cookies=cookies,params=params,data=body)
    elif method.upper() == 'DELETE':
        res = self.request.delete_request(url=url,headers=headers,cookies=cookies,params=params,data=body)
    else:
        pass # 待扩展
        
    if saves:
        # 遍历saves
        for save in saves.split(";"):
            # 切割字符串 如 key=$.data
            key = save.split("=")[0]
            jsp = save.split("=")[1]
            self.save_date(res.json(), key+"-"+"{id}", jsp)
    if verify:
        # 遍历verify:
        for ver in verify.split(";"):
            expr = ver.split("=")[0]
            # 判断Jsonpath还是正则断言
            if expr.startswith("$."):
                actual = jsonpath.jsonpath(res.json(), expr)
                if not actual:
                    raise KeyError("该jsonpath未匹配到值,请确认接口响应和jsonpath正确性")
                actual = actual[0]
            else:
                actual = re.findall(expr,res.text)[0]
            expect = ver.split("=")[1]
            self.request.assertEquals(actual, expect)

    if db_connect:
        # 执行teardown_sql
        self.execute_teardown_sql(db_connect,teardown_sql)

    if redis_db_connect:
        # 执行teardown_redis操作
        self.execute_redis_get(redis_db_connect,teardown_sql)

    #最后关闭mysql数据库连接
    if db_connect:
        db_connect.db.close()
        
        '''
                 )


    @classmethod
    def tearDownClass(cls):
        pass




