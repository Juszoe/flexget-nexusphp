# coding=utf-8
from __future__ import unicode_literals, division, absolute_import
from builtins import *

import concurrent.futures

from requests.adapters import HTTPAdapter

from flexget import plugin
from flexget.config_schema import one_or_more
from flexget.event import event
from flexget.utils.soup import get_soup


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
            'comment': {'type': 'boolean'}
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

        def consider_entry(_entry, _link):
            discount, seeders, leechers, hr = NexusPHP._get_info(task, _link, config['cookie'], config['adapter'])
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
                raise exception

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

        soup = get_soup(peer_page.content)
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
                        if text == '用户' or text == '用戶':
                            name_index = i
                        elif text == '可连接' or text == '可連接':
                            connectable_index = i
                        elif text == '上传' or text == '上傳':
                            uploaded_index = i
                        elif text == '下载' or text == '下載':
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
                pass
        return peers

    @staticmethod
    def _get_info(task, link, cookie, adapter):
        headers = {
            'cookie': cookie,
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/75.0.3770.142 Safari/537.36'
        }
        detail_page = task.requests.get(link, headers=headers, allow_redirects=False)  # 详情
        peer_url = link.replace('details.php', 'viewpeerlist.php', 1)
        peer_page = task.requests.get(peer_url, headers=headers, allow_redirects=False)  # peer详情

        if 'login' in detail_page.url or 'login' in peer_page.url:
            raise plugin.PluginError("Can't access the site. Your cookie may be wrong!")

        if adapter:
            convert = {value: key for key, value in adapter.items()}
            discount_fn = NexusPHP.generate_discount_fn(convert)
            return NexusPHP.info_from_page(detail_page, peer_page, discount_fn)

        sites_discount = {
            'chdbits': {
                'pro_free': 'free',
                'pro_2up': '2x',
                'pro_free2up': '2xfree',
                'pro_30pctdown': '30%',
                'pro_50pctdown': '50%',
                'pro_50pctdown2up': '2x50%'
            },
            'u2.dmhy': {
                'pro_free': 'free',
                'pro_2up': '2x',
                'pro_free2up': '2xfree',
                'pro_30pctdown': '30%',
                'pro_50pctdown': '50%',
                'pro_50pctdown2up': '2x50%',
                'pro_custom': '2x'
            },
            'yingk': {
                'span_frees': 'free',
                'span_twoupls': '2x',
                'span_twoupfreels': '2xfree',
                'span_thirtypercentls': '30%',
                'span_halfdowns': '50%',
                'span_twouphalfdownls': '2x50%'
            }
        }
        for site, convert in sites_discount.items():
            if site in link:
                discount_fn = NexusPHP.generate_discount_fn(convert)
                return NexusPHP.info_from_page(detail_page, peer_page, discount_fn)
        discount_fn = NexusPHP.generate_discount_fn({
            'free': 'free',
            'twoup': '2x',
            'twoupfree': '2xfree',
            'thirtypercent': '30%',
            'halfdown': '50%',
            'twouphalfdown': '2x50%'
        })
        return NexusPHP.info_from_page(detail_page, peer_page, discount_fn)

    @staticmethod
    def generate_discount_fn(convert):
        def fn(page):
				'''
                if key in page.text:
                    return value
                '''
				# by csupxh 2019.08.31
				# 仅匹配id为top节点的折扣信息，防止误匹配到该折扣信息的其它版本种子（种子详情页下面有一个'其它版本'表）
                sp = get_soup(page.text)
                top = sp.find(id='top')
                if top is not None and key in top.decode():
                    return value
            return None

        return fn


@event('plugin.register')
def register_plugin():
    plugin.register(NexusPHP, 'nexusphp', api_ver=2)
