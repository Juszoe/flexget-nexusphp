from __future__ import unicode_literals, division, absolute_import

import concurrent.futures

from flexget import plugin
from flexget.config_schema import one_or_more
from flexget.event import event
from flexget.utils.soup import get_soup


class NexusPHP(object):
    """
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
    """

    schema = {
        'type': 'object',
        'properties': {
            'cookie': {'type': 'string'},
            'discount': one_or_more({'type': 'string', 'enum': ['free', '2x', '2xfree', '30%', '50%', '2x50%']}),
            'seeders': {
                'type': 'object',
                'properties': {
                    'min': {'type': 'integer', 'minimum': 0},
                    'max': {'type': 'integer', 'minimum': 0}
                }
            },
            'leechers': {
                'type': 'object',
                'properties': {
                    'min': {'type': 'integer', 'minimum': 0},
                    'max': {'type': 'integer', 'minimum': 0},
                    'max_complete': {'type': 'number', 'minimum': 0, 'maximum': 1}
                }
            }
        },
        'required': ['cookie']
    }

    def build_conifg(self, config):
        config = dict(config)
        config.setdefault('discount', None)
        config.setdefault('seeders', {'min': 0, 'max': 100000})
        config['seeders'].setdefault('min', 0)
        config['seeders'].setdefault('max', 100000)
        config.setdefault('leechers', {'min': 0, 'max': 100000, 'max_complete': 1})
        config['leechers'].setdefault('min', 0)
        config['leechers'].setdefault('max', 100000)
        config['leechers'].setdefault('max_complete', 1)
        return config

    @plugin.priority(-1)
    def on_task_filter(self, task, config):
        config = self.build_conifg(config)

        def consider_entry(_entry, _link):
            discount, seeders, leechers = NexusPHP._get_info(task, _link, config['cookie'])
            seeder_max = config['seeders']['max']
            seeder_min = config['seeders']['min']
            leecher_max = config['leechers']['max']
            leecher_min = config['leechers']['min']

            if config['discount']:
                if discount not in config['discount']:
                    _entry.reject('%s does not match discount' % discount)  # 优惠信息不匹配
                    return

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
    def info_from_page(detail_page, peer_page):
        soup = get_soup(detail_page.content, 'html.parser')
        try:
            discount_class = soup.find('h1', id='top').b.font['class'][0]  # selector: '#top > b:nth-child(1) > font'
            discount_table = {
                'free': 'free',
                'twoup': '2x',
                'twoupfree': '2xfree',
                'thirtypercent': '30%',
                'halfdown': '50%',
                'twouphalfdown': '2x50%'
            }
            discount = discount_table[discount_class]
        except AttributeError:
            discount = None  # 无优惠

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
                except IndexError:
                    pass
                except ValueError:
                    pass
            return peers

        soup = get_soup(peer_page.content)
        tables = soup.find_all('table', limit=2)
        try:
            seeders = get_peers(tables[0])
        except IndexError:
            seeders = []
        try:
            leechers = get_peers(tables[1])
        except IndexError:
            leechers = []

        return discount, seeders, leechers

    @staticmethod
    def _get_info(task, link, cookie):
        headers = {
            'cookie': cookie,
            'accept-encoding': 'gzip, deflate',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/75.0.3770.142 Safari/537.36'
        }
        detail_page = task.requests.get(link, headers=headers, allow_redirects=False)  # 详情
        peer_url = link.replace('details.php', 'viewpeerlist.php', 1)
        peer_page = task.requests.get(peer_url, headers=headers, allow_redirects=False)  # peer详情

        if detail_page.status_code == 302 or peer_page.status_code == 302:
            raise plugin.PluginError("Can't access the site. Your cookie may be wrong!")

        return NexusPHP.info_from_page(detail_page, peer_page)


@event('plugin.register')
def register_plugin():
    plugin.register(NexusPHP, 'nexusphp', api_ver=2)
