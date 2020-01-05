# coding=utf-8
from __future__ import unicode_literals, division, absolute_import
from builtins import *

import concurrent.futures
import re
import logging
from requests.adapters import HTTPAdapter

from flexget import plugin
from flexget.config_schema import one_or_more
from flexget.event import event
from flexget.utils.soup import get_soup


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
            'cookie': {'type': 'string'},
            'discount': one_or_more({'type': 'string', 'enum': ['free', '2x', '2xfree', '30%', '50%', '2x50%']}),
            'seeders': {
                'type': 'object',
                'properties': {
                    'min': {'type': 'integer', 'minimum': 0, 'default': 0},
                    'max': {'type': 'integer', 'minimum': 0, 'default': 100000}
                }
            },
            'leechers': {
                'type': 'object',
                'properties': {
                    'min': {'type': 'integer', 'minimum': 0, 'default': 0},
                    'max': {'type': 'integer', 'minimum': 0, 'default': 100000},
                    'max_complete': {'type': 'number', 'minimum': 0, 'maximum': 1, 'default': 1}
                }
            },
            'hr': {'type': 'boolean'},
            'adapter': {
                'type': 'object',
                'properties': {
                    'free': {'type': 'string', 'default': 'free'},
                    '2x': {'type': 'string', 'default': 'twoup'},
                    '2xfree': {'type': 'string', 'default': 'twoupfree'},
                    '30%': {'type': 'string', 'default': 'thirtypercent'},
                    '50%': {'type': 'string', 'default': 'halfdown'},
                    '2x50%': {'type': 'string', 'default': 'twouphalfdown'}
                }
            },
            'comment': {'type': 'boolean'},
            'user-agent': {'type': 'string'}
        },
        'required': ['cookie']
    }

    @staticmethod
    def build_config(config):
        config = dict(config)
        config.setdefault('discount', None)
        config.setdefault('seeders', {'min': 0, 'max': 100000})
        config.setdefault('leechers', {'min': 0, 'max': 100000, 'max_complete': 1})
        config.setdefault('hr', True)
        config.setdefault('adapter', None)
        config.setdefault('user-agent',
                          'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/75.0.3770.142 Safari/537.36')
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

        # 先访问一次 预防异常
        headers = {
            'cookie': config['cookie'],
            'user-agent': config['user-agent']
        }
        try:
            task.requests.get(task.entries[0].get('link'), headers=headers)
        except:
            pass

        def consider_entry(_entry, _link):
            try:
                discount, seeders, leechers, hr = NexusPHP._get_info(
                    task, _link, config['cookie'], config['adapter'], config['user-agent'])
            except plugin.PluginError as e:
                raise e
            except Exception as e:
                log.info('NexusPHP._get_info: ' + str(e))
                return

            seeder_max = config['seeders']['max']
            seeder_min = config['seeders']['min']
            leecher_max = config['leechers']['max']
            leecher_min = config['leechers']['min']

            if config['discount']:
                if discount not in config['discount']:
                    _entry.reject('%s does not match discount' % discount)  # 优惠信息不匹配
                    return

            if config['hr'] is False and hr:
                _entry.reject('it is HR')  # 拒绝HR

            if len(seeders) not in range(seeder_min, seeder_max + 1):
                _entry.reject('%d is out of range of seeder' % len(seeders))  # 做种人数不匹配
                return

            if len(leechers) not in range(leecher_min, leecher_max + 1):
                _entry.reject('%d is out of range of leecher' % len(leechers))  # 下载人数不匹配
                return

            if len(leechers) != 0:
                max_complete = max(leechers, key=lambda x: x['completed'])['completed']
            else:
                max_complete = 0
            if max_complete > config['leechers']['max_complete']:
                _entry.reject('%f is more than max_complete' % max_complete)  # 最大完成度不匹配
                return

            _entry.accept()

        futures = []  # 线程任务
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for entry in task.entries:
                link = entry.get('link')
                if not link:
                    raise plugin.PluginError("The rss plugin require 'other_fields' which contain 'link'. "
                                             "For example: other_fields: - link")
                futures.append(executor.submit(consider_entry, entry, link))

        for f in concurrent.futures.as_completed(futures):
            exception = f.exception()
            if isinstance(exception, plugin.PluginError):
                log.info(exception)

    @staticmethod
    # 解析页面，获取优惠、做种者信息、下载者信息
    def info_from_page(detail_page, peer_page, discount_fn, hr_fn=None):
        try:
            discount = discount_fn(detail_page)
        except Exception:
            discount = None  # 无优惠

        try:
            if hr_fn:
                hr = hr_fn(detail_page)
            else:
                hr = False
                for item in ['hitandrun', 'hit_run.gif', 'Hit and Run', 'Hit & Run']:
                    if item in detail_page.text:
                        hr = True
                        break
        except Exception:
            hr = False  # 无HR

        soup = get_soup(peer_page)
        tables = soup.find_all('table', limit=2)
        try:
            seeders = NexusPHP.get_peers(tables[0])
        except IndexError:
            seeders = []
        try:
            leechers = NexusPHP.get_peers(tables[1])
        except IndexError:
            leechers = []

        return discount, seeders, leechers, hr

    @staticmethod
    def get_peers(table):
        peers = []
        name_index = 0
        connectable_index = 1
        uploaded_index = 2
        downloaded_index = 4
        completed_index = 7
        for index, tr in enumerate(table.find_all('tr')):
            try:
                if index == 0:
                    tds = tr.find_all('td')
                    for i, td in enumerate(tds):
                        text = td.get_text()
                        if text in ['用户', '用戶', '会员/IP']:
                            name_index = i
                        elif text in ['可连接', '可連接', '公网']:
                            connectable_index = i
                        elif text in ['上传', '上傳', '总上传']:
                            uploaded_index = i
                        elif text in ['下载', '下載', '本次下载']:
                            downloaded_index = i
                        elif text == '完成':
                            completed_index = i
                else:
                    tds = tr.find_all('td')
                    peers.append({
                        'name': tds[name_index].get_text(),
                        'connectable': True if tds[connectable_index].get_text() != '是' else False,
                        'uploaded': tds[uploaded_index].get_text(),
                        'downloaded': tds[downloaded_index].get_text(),
                        'completed': float(tds[completed_index].get_text().strip('%')) / 100
                    })
            except Exception:
                peers.append({
                        'name': '',
                        'connectable': False,
                        'uploaded': '',
                        'downloaded': '',
                        'completed': 0
                    })
        return peers

    @staticmethod
    def _get_info(task, link, cookie, adapter, user_agent):
        headers = {
            'cookie': cookie,
            'user-agent': user_agent
        }
        detail_page = task.requests.get(link, headers=headers)  # 详情
        detail_page.encoding = 'utf-8'
        if 'totheglory' in link:
            peer_url = link
        else:
            peer_url = link.replace('details.php', 'viewpeerlist.php', 1)
        try:
            peer_page = task.requests.get(peer_url, headers=headers).text  # peer详情
        except:
            peer_page = ''

        if 'login' in detail_page.url:
            raise plugin.PluginError("Can't access the site. Your cookie may be wrong!")

        if adapter:
            convert = {value: key for key, value in adapter.items()}
            discount_fn = NexusPHP.generate_discount_fn(convert)
            return NexusPHP.info_from_page(detail_page, peer_page, discount_fn)

        sites_discount = {
            'chdbits': {
                'pro_free.*?</h1>': 'free',
                'pro_2up.*?</h1>': '2x',
                'pro_free2up.*?</h1>': '2xfree',
                'pro_30pctdown.*?</h1>': '30%',
                'pro_50pctdown.*?</h1>': '50%',
                'pro_50pctdown2up.*?</h1>': '2x50%'
            },
            'u2.dmhy': {
                '<td.*?top.*?pro_free.*?优惠历史.*?</td>': 'free',
                '<td.*?top.*?pro_2up.*?优惠历史.*?</td>': '2x',
                '<td.*?top.*?pro_free2up.*?优惠历史.*?</td>': '2xfree',
                '<td.*?top.*?pro_30pctdown.*?优惠历史.*?</td>': '30%',
                '<td.*?top.*?pro_50pctdown.*?优惠历史.*?</td>': '50%',
                '<td.*?top.*?pro_50pctdown2up.*?优惠历史.*?</td>': '2x50%',
                '<td.*?top.*?pro_custom.*?优惠历史.*?</td>': '2xfree'
            },
            'yingk': {
                'span_frees': 'free',
                'span_twoupls': '2x',
                'span_twoupfreels': '2xfree',
                'span_thirtypercentls': '30%',
                'span_halfdowns': '50%',
                'span_twouphalfdownls': '2x50%'
            },
            'totheglory': {
                '本种子限时不计流量': 'free',
                '本种子的下载流量计为实际流量的30%': '30%',
                '本种子的下载流量会减半': '50%',
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
        for site, convert in sites_discount.items():
            if site in link:
                discount_fn = NexusPHP.generate_discount_fn(convert)
                return NexusPHP.info_from_page(detail_page, peer_page, discount_fn)
        discount_fn = NexusPHP.generate_discount_fn({
            'class=\'free\'.*?免.*?</h1>': 'free',
            'class=\'twoup\'.*?2X.*?</h1>': '2x',
            'class=\'twoupfree\'.*?2X免.*?</h1>': '2xfree',
            'class=\'thirtypercent\'.*?30%.*?</h1>': '30%',
            'class=\'halfdown\'.*?50%.*?</h1>': '50%',
            'class=\'twouphalfdown\'.*?2X 50%.*?</h1>': '2x50%'
        })
        return NexusPHP.info_from_page(detail_page, peer_page, discount_fn)

    @staticmethod
    def generate_discount_fn(convert):
        def fn(page):
            html = page.text.replace('\n', '')
            for key, value in convert.items():
                match = re.search(key, html)
                if match:
                    return value
            return None

        return fn


@event('plugin.register')
def register_plugin():
    plugin.register(NexusPHP, 'nexusphp', api_ver=2)
