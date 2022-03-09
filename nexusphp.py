# coding=utf-8
from __future__ import unicode_literals, division, absolute_import

import time
from builtins import *

import concurrent.futures
import re
import logging
from datetime import datetime
from unittest import result

from requests.adapters import HTTPAdapter

from flexget import plugin
from flexget.config_schema import one_or_more
from flexget.event import event
from flexget.utils.soup import get_soup
from flexget.utils.tools import parse_timedelta

log = logging.getLogger('nexusphp')


class NexusPHP(object):
    """
    配置示例
    task_name:
        rss:
            url: https://www.example.com/rss.xml
            other_fields:
                - link
        nexusphp:
            cookie: 'my_cookie'
            discount:
                - free
                - 2x
            seeders:
                min: 1
                max: 30
            leechers:
                min: 1
                max: 100
                max_complete: 0.8
            hr: no
    """

    schema = {
        'type': 'object',
        'properties': {
            'cookie': {
                'type': 'string'
            },
            'discount': one_or_more({
                'type': 'string',
                'enum': ['free', '2x', '2xfree', '30%', '50%', '2x50%']
            }),
            'seeders': {
                'type': 'object',
                'properties': {
                    'min': {
                        'type': 'integer',
                        'minimum': 0,
                        'default': 0
                    },
                    'max': {
                        'type': 'integer',
                        'minimum': 0,
                        'default': 100000
                    }
                }
            },
            'leechers': {
                'type': 'object',
                'properties': {
                    'min': {
                        'type': 'integer',
                        'minimum': 0,
                        'default': 0
                    },
                    'max': {
                        'type': 'integer',
                        'minimum': 0,
                        'default': 100000
                    },
                    'max_complete': {
                        'type': 'number',
                        'minimum': 0,
                        'maximum': 1,
                        'default': 1
                    }
                }
            },
            'left-time': {
                'type': 'string',
                'format': 'interval'
            },
            'hr': {
                'type': 'boolean'
            },
            'adapter': {
                'type': 'object',
                'properties': {
                    'free': {
                        'type': 'string',
                        'default': 'free'
                    },
                    '2x': {
                        'type': 'string',
                        'default': 'twoup'
                    },
                    '2xfree': {
                        'type': 'string',
                        'default': 'twoupfree'
                    },
                    '30%': {
                        'type': 'string',
                        'default': 'thirtypercent'
                    },
                    '50%': {
                        'type': 'string',
                        'default': 'halfdown'
                    },
                    '2x50%': {
                        'type': 'string',
                        'default': 'twouphalfdown'
                    }
                }
            },
            'comment': {
                'type': 'boolean'
            },
            'user-agent': {
                'type': 'string'
            },
            'remember': {
                'type': 'boolean',
                'default': True
            }
        },
        'required': ['cookie']
    }

    @staticmethod
    def build_config(config):
        config = dict(config)
        config.setdefault('discount', None)
        config.setdefault('seeders', None)
        config.setdefault('leechers', None)
        config.setdefault('left-time', None)
        config.setdefault('hr', True)
        config.setdefault('adapter', None)
        config.setdefault('user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ' 'Chrome/75.0.3770.142 Safari/537.36')
        return config

    @plugin.priority(127)
    def on_task_modify(self, task, config):
        if config.get('comment', False):
            for entry in task.entries:
                if 'torrent' in entry and 'link' in entry:
                    entry['torrent'].content['comment'] = entry['link']
                    entry['torrent'].modified = True

    def on_task_filter(self, task, config):
        config = self.build_config(config)

        adapter = HTTPAdapter(max_retries=5)
        task.requests.mount('http://', adapter)
        task.requests.mount('https://', adapter)
        task.requests.headers.update({'cookie': config['cookie'], 'user-agent': config['user-agent']})

        # 先访问一次 预防异常
        try:
            task.requests.get(task.entries[0].get('link'))
        except Exception as e:
            log.info('NexusPHP.on_task_filter: ' + str(e))
            pass

        def consider_entry(_entry, _link):
            try:
                discount, seeder_num, leecher_num, hr, expired_time = NexusPHP._get_info(task, _link, config)
            except plugin.PluginError as e:
                log.info('NexusPHP._get_info.plugin.PluginError: ' + str(e))
            except Exception as e:
                log.info('NexusPHP._get_info: ' + str(e))
                return

            remember = config['remember']

            if config['discount']:
                log.info("config['discount']: " + str(config['discount']) + ", discount: " + str(discount))
                if discount not in config['discount']:
                    _entry.reject('%s does not match discount' % discount, remember=remember)  # 优惠信息不匹配
                    return
            if config['left-time'] and expired_time:
                left_time = expired_time - datetime.now()
                # 实际剩余时间 < 'left-time'
                if left_time < parse_timedelta(config['left-time']):
                    _entry.reject('its discount time only left [%s]' % left_time, remember=remember)  # 剩余时间不足
                    return

            if config['hr'] is False and hr:
                _entry.reject('it is HR', remember=True)  # 拒绝HR

            if config['seeders']:
                seeder_max = config['seeders']['max']
                seeder_min = config['seeders']['min']
                log.info("msg config seeder_max:" + str(seeder_max) + "  seeder_min:" + str(seeder_min))
                # log.info("msg seeders:" + str(seeder_num) + ",  " + str(range(seeder_min - 1, seeder_max + 1)))
                if seeder_num not in range(seeder_min, seeder_max + 1):
                    _entry.reject('%d is out of range of seeder' % seeder_num, remember=True)  # 做种人数不匹配
                    return

            if config['leechers']:
                leecher_max = config['leechers']['max']
                leecher_min = config['leechers']['min']
                log.info("msg conifg leecher_max:" + str(leecher_max) + "  leecher_min:" + str(leecher_min))
                if leecher_num not in range(leecher_min, leecher_max + 1):
                    _entry.reject('%d is out of range of leecher' % leecher_num, remember=True)  # 下载人数不匹配
                    return

                if leecher_num != 0:
                    max_complete = max(leecher_num, key=lambda x: x['completed'])['completed']
                else:
                    max_complete = 0
                if max_complete > config['leechers']['max_complete']:
                    _entry.reject('%f is more than max_complete' % max_complete, remember=True)  # 最大完成度不匹配
                    return


            _entry.accept()

        futures = []  # 线程任务
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            for entry in task.accepted + task.undecided:
                link = entry.get('link')
                if not link:
                    raise plugin.PluginError("The rss plugin require 'other_fields' which contain 'link'. " "For example: other_fields: - link")
                futures.append(executor.submit(consider_entry, entry, link))
                time.sleep(0.5)

        for f in concurrent.futures.as_completed(futures):
            exception = f.exception()
            if isinstance(exception, plugin.PluginError):
                log.error(exception)

    @ staticmethod
    # 解析页面，获取优惠、做种者信息、下载者信息
    def info_from_page(detail_page, discount_fn, hr_fn):
        try:
            discount, expired_time = discount_fn(detail_page)

            if hr_fn:
                hr = hr_fn(detail_page)
            else:
                hr = False
                for item in ['hitandrun', 'hit_run.gif', 'Hit and Run', 'Hit & Run']:
                    if item in detail_page.text:
                        hr = True
                        break
        except plugin.PluginError as e:
            log.info('PluginError by info_from_page , e: ' + str(e))
            raise e
        except Exception as e:
            discount = expired_time = None  # 无优惠
            hr = False  # 无HR
            log.info('Exception by info_from_page , e: ' + str(e))

        htmlStr = detail_page.text
        peer_str_arr = re.findall(r'[0-9]+.{0,3}做.者.{1,10}[0-9]+.{0,3}下.者', htmlStr)
        result_str = ''
        seeder_num = 0
        leecher_num = 0
        if len(peer_str_arr):
            result_str = peer_str_arr[-1]
            peerStr = re.findall(r'[0-9]+', result_str)
            if len(peerStr) == 2:
                seeder_num = int(peerStr[0])
                leecher_num = int(peerStr[1])
        log.info('msg seeder_num: ' + str(seeder_num) + ', leecher_num:' + str(leecher_num))
        return discount, seeder_num, leecher_num, hr, expired_time

    @ staticmethod
    def _get_info(task, link, config):
        if 'open.cd' in link:
            link = link.replace('details.php', 'plugin_details.php')
        detail_page = task.requests.get(link, timeout=20)  # 详情
        detail_page.encoding = 'utf-8'

        if 'login' in detail_page.url or 'portal.php' in detail_page.url:
            raise plugin.PluginError("Can't access the site. Your cookie may be wrong!")

        # 1. HR
        hr_fn = None
        if 'chdbits' in link:
            def chd_hr_fn(_page):
                if '<b>H&R' in _page.text:
                    return True
                return False
            hr_fn = chd_hr_fn

        # 2. discount
        sites_discount = {
            'chdbits': {
                'pro_free2up.*?</h1>': '2xfree',
                'pro_free.*?</h1>': 'free',
                'pro_2up.*?</h1>': '2x',
                'pro_50pctdown2up.*?</h1>': '2x50%',
                'pro_30pctdown.*?</h1>': '30%',
                'pro_50pctdown.*?</h1>': '50%'
            },
            'u2.dmhy': {
                'class=.pro_2up.*?promotion.*?</td>': '2x',
                'class=.pro_free2up.*?promotion.*?</td>': '2xfree',
                'class=.pro_free.*?promotion.*?</td>': 'free',
                'class=.pro_50pctdown2up.*?promotion.*?</td>': '2x50%',
                'class=.pro_30pctdown.*?promotion.*?</td>': '30%',
                'class=.pro_50pctdown.*?promotion.*?</td>': '50%',
                r'class=.pro_custom.*?0\.00X.*?promotion.*?</td>': '2xfree'
            },
            'totheglory': {
                '本种子限时不计流量.*?</font>': 'free',
                '本种子的下载流量计为实际流量的30%.*?</font>': '30%',
                '本种子的下载流量会减半.*?</font>': '50%',
            },
            'open.cd': {
                'pro_free2up': '2xfree',
                'pro_free': 'free',
                'pro_2up': '2x',
                'pro_50pctdown2up': '2x50%',
                'pro_30pctdown': '30%',
                'pro_50pctdown': '50%'
            },
            'hdchina': {
                'pro_free.*?</h2>': 'free',
                'pro_2up.*?</h2>': '2x',
                'pro_free2up.*?</h2>': '2xfree',
                'pro_30pctdown.*?</h2>': '30%',
                'pro_50pctdown.*?</h2>': '50%',
                'pro_50pctdown2up.*?</h2>': '2x50%'
            }
        }

        discount_fn = NexusPHP.generate_discount_fn({
            'class=\'free\'.*?免.*?</h1>': 'free',
            'class=\'twoup\'.*?2X.*?</h1>': '2x',
            'class=\'twoupfree\'.*?2X免.*?</h1>': '2xfree',
            'class=\'thirtypercent\'.*?30%.*?</h1>': '30%',
            'class=\'halfdown\'.*?50%.*?</h1>': '50%',
            'class=\'twouphalfdown\'.*?2X 50%.*?</h1>': '2x50%'
        })
        for site, convert in sites_discount.items():
            if site in link:
                discount_fn = NexusPHP.generate_discount_fn(convert)
                break

        if 'hdchina' in link:
            def _(page):
                return NexusPHP.get_discount_from_hdchina(page, task)

            discount_fn = _

        if config['adapter']:
            convert = {value: key for key, value in config['adapter'].items()}
            discount_fn = NexusPHP.generate_discount_fn(convert)

        return NexusPHP.info_from_page(detail_page, discount_fn, hr_fn)

    @ staticmethod
    def get_discount_from_hdchina(details_page, task):
        soup = get_soup(details_page.text, 'html5lib')
        csrf = soup.find('meta', attrs={'name': 'x-csrf'})['content']
        torrent_id = str(soup.find('div', class_='details_box').find('span', class_='sp_state_placeholder')['id'])

        res = task.requests.post('https://hdchina.org/ajax_promotion.php', data={
            'ids[]': torrent_id,
            'csrf': csrf,
        }, timeout=20)
        """ sample response
        {
            'status': 200,
            'message': {
                '530584': {
                    'sp_state': '<p style="display: none"> <img class="pro_free" src="pic/trans.gif" alt="Free" onmouseover="domTT_activate(this, event, \'content\', \'<b><font class=&quot;free&quot;>免费</font></b>',
                    'timeout': ''
                }
            }
        }
        """
        if res.status_code != 200:
            return None, None

        res = res.json()
        if res['status'] != 200:
            return None, None

        discount_info = res['message'][torrent_id]
        # log.info('discount_info: ' + str(discount_info))
        if 'sp_state' not in discount_info or not discount_info['sp_state']:
            return None, None
        if '<p style="display: none">' in discount_info['sp_state']:
            # HDC cookie 仅部分错误时会直接返回free
            # 同时带有特征 <p style="display: none">
            # 也许是站点的BUG
            raise plugin.PluginError("Can't HDChina access the site. Your cookie may be wrong!")

        expired_time = None
        match = re.search(r'(\d{4})(-\d{1,2}){2}\s\d{1,2}(:\d{1,2}){2}', discount_info['timeout'])
        if match:
            expired_time_str = match.group(0)
            expired_time = datetime.strptime(expired_time_str, "%Y-%m-%d %H:%M:%S")

        discount_mapping = {
            'class="pro_free2up"': '2xfree',
            'class="pro_free"': 'free',
            'class="pro_2up"': '2x',
            'class="pro_50pctdown2up"': '2x50%',
            'class="pro_30pctdown"': '30%',
            'class="pro_50pctdown"': '50%'
        }

        for key, value in discount_mapping.items():
            if key in discount_info['sp_state']:
                return value, expired_time

        return None, None

    @ staticmethod
    def generate_discount_fn(convert):
        def fn(page):
            html = page.text.replace('\n', '')
            for key, value in convert.items():
                match = re.search(key, html)
                if match:
                    discount_str = match.group(0)
                    expired_time = None
                    # 匹配优惠剩余时间
                    match = re.search(r'(\d{4})(-\d{1,2}){2}\s\d{1,2}(:\d{1,2}){2}', discount_str)
                    if match:
                        expired_time_str = match.group(0)
                        expired_time = datetime.strptime(expired_time_str, "%Y-%m-%d %H:%M:%S")
                    return value, expired_time
            return None, None

        return fn


@ event('plugin.register')
def register_plugin():
    plugin.register(NexusPHP, 'nexusphp', api_ver=2)
