#!/usr/bin/env python
# -*- coding: utf-8 -*-


from flask import Blueprint, request
import json
from uuid import uuid4
import jimit as ji

from models import Guest
from models.initialize import app, dev_table
from models import Database as db
from models import Config
from models import GuestDisk
from models import Rules
from models import Utils


__author__ = 'James Iter'
__date__ = '2017/4/24'
__contact__ = 'james.iter.cn@gmail.com'
__copyright__ = '(c) 2017 by James Iter.'


blueprint = Blueprint(
    'disk',
    __name__,
    url_prefix='/api/disk'
)

blueprints = Blueprint(
    'disks',
    __name__,
    url_prefix='/api/disks'
)


@Utils.dumps2response
def r_create():

    args_rules = [
        Rules.DISK_SIZE.value
    ]

    try:
        ji.Check.previewing(args_rules, request.json)

        ret = dict()
        ret['state'] = ji.Common.exchange_state(20000)

        size = request.json['size']

        if size < 1:
            ret['state'] = ji.Common.exchange_state(41255)
            return ret

        guest_disk = GuestDisk()
        guest_disk.guest_uuid = ''
        guest_disk.size = size
        guest_disk.uuid = uuid4().__str__()
        guest_disk.label = ji.Common.generate_random_code(length=8)
        guest_disk.sequence = -1
        guest_disk.format = 'qcow2'

        config = Config()
        config.id = 1
        config.get()

        image_path = '/'.join(['DiskPool', guest_disk.uuid + '.' + guest_disk.format])

        message = {'action': 'create_disk', 'glusterfs_volume': config.glusterfs_volume,
                   'image_path': image_path, 'size': guest_disk.size}

        db.r.rpush(app.config['downstream_queue'], json.dumps(message, ensure_ascii=False))

        guest_disk.create()

        return ret

    except ji.PreviewingError, e:
        return json.loads(e.message)


@Utils.dumps2response
def r_resize(uuid, size):

    args_rules = [
        Rules.UUID.value,
        Rules.DISK_SIZE_STR.value
    ]

    try:
        ji.Check.previewing(args_rules, {'uuid': uuid, 'size': size})

        guest_disk = GuestDisk()
        guest_disk.uuid = uuid
        guest_disk.get_by('uuid')

        used = True

        if guest_disk.guest_uuid.__len__() != 36:
            used = False

        ret = dict()
        ret['state'] = ji.Common.exchange_state(20000)

        if guest_disk.size >= size:
            ret['state'] = ji.Common.exchange_state(41257)
            return ret

        guest_disk.size = size
        guest_disk.update()

        message = {'action': 'resize_disk', 'size': size}

        if used:
            message['uuid'] = guest_disk.guest_uuid
            message['device_node'] = dev_table[guest_disk.sequence]
            Guest.emit_instruction(message=json.dumps(message))
        else:
            config = Config()
            config.id = 1
            config.get()

            image_path = '/'.join(['DiskPool', guest_disk.uuid + '.' + guest_disk.format])
            message['glusterfs_volume'] = config.glusterfs_volume
            message['image_path'] = image_path

            db.r.rpush(app.config['downstream_queue'], json.dumps(message, ensure_ascii=False))

        return ret

    except ji.PreviewingError, e:
        return json.loads(e.message)


@Utils.dumps2response
def r_delete(uuid):

    args_rules = [
        Rules.UUID.value
    ]

    try:
        ji.Check.previewing(args_rules, {'uuid': uuid})

        guest_disk = GuestDisk()
        guest_disk.uuid = uuid
        guest_disk.get_by('uuid')

        ret = dict()
        ret['state'] = ji.Common.exchange_state(20000)

        if guest_disk.guest_uuid.__len__() > 0:
            ret['state'] = ji.Common.exchange_state(41256)
            return ret

        config = Config()
        config.id = 1
        config.get()

        image_path = '/'.join(['DiskPool', guest_disk.uuid + '.' + guest_disk.format])

        message = {'action': 'delete_disk', 'glusterfs_volume': config.glusterfs_volume, 'image_path': image_path}
        db.r.rpush(app.config['downstream_queue'], json.dumps(message, ensure_ascii=False))

        guest_disk.delete()

        return ret

    except ji.PreviewingError, e:
        return json.loads(e.message)


@Utils.dumps2response
def r_get_by_filter():
    page = str(request.args.get('page', 1))
    page_size = str(request.args.get('page_size', 50))

    args_rules = [
        Rules.PAGE.value,
        Rules.PAGE_SIZE.value
    ]

    try:
        ji.Check.previewing(args_rules, {'page': page, 'page_size': page_size})
    except ji.PreviewingError, e:
        return json.loads(e.message)

    page = int(page)
    page_size = int(page_size)

    # 把page和page_size换算成offset和limit
    offset = (page - 1) * page_size
    # offset, limit将覆盖page及page_size的影响
    offset = str(request.args.get('offset', offset))
    limit = str(request.args.get('limit', page_size))

    order_by = request.args.get('order_by', 'id')
    order = request.args.get('order', 'asc')
    filter_str = request.args.get('filter', '')

    args_rules = [
        Rules.OFFSET.value,
        Rules.LIMIT.value,
        Rules.ORDER_BY.value,
        Rules.ORDER.value
    ]

    try:
        ji.Check.previewing(args_rules, {'offset': offset, 'limit': limit, 'order_by': order_by, 'order': order})
        offset = int(offset)
        limit = int(limit)
        ret = dict()
        ret['state'] = ji.Common.exchange_state(20000)
        ret['data'] = list()
        ret['paging'] = {'total': 0, 'offset': offset, 'limit': limit, 'page': page, 'page_size': page_size,
                         'next': '', 'prev': '', 'first': '', 'last': ''}

        ret['data'], ret['paging']['total'] = GuestDisk.get_by_filter(offset=offset, limit=limit, order_by=order_by,
                                                                      order=order, filter_str=filter_str)

        host_url = request.host_url.rstrip('/')
        other_str = '&filter=' + filter_str + '&order=' + order + '&order_by=' + order_by
        last_pagination = (ret['paging']['total'] + page_size - 1) / page_size

        if page <= 1:
            ret['paging']['prev'] = host_url + blueprints.url_prefix + '?page=1&page_size=' + page_size.__str__() + \
                                    other_str
        else:
            ret['paging']['prev'] = host_url + blueprints.url_prefix + '?page=' + str(page-1) + '&page_size=' + \
                                    page_size.__str__() + other_str

        if page >= last_pagination:
            ret['paging']['next'] = host_url + blueprints.url_prefix + '?page=' + last_pagination.__str__() + \
                                    '&page_size=' + page_size.__str__() + other_str
        else:
            ret['paging']['next'] = host_url + blueprints.url_prefix + '?page=' + str(page+1) + '&page_size=' + \
                                    page_size.__str__() + other_str

        ret['paging']['first'] = host_url + blueprints.url_prefix + '?page=1&page_size=' + \
            page_size.__str__() + other_str
        ret['paging']['last'] = \
            host_url + blueprints.url_prefix + '?page=' + last_pagination.__str__() + '&page_size=' + \
            page_size.__str__() + other_str

        return ret
    except ji.PreviewingError, e:
        return json.loads(e.message)


@Utils.dumps2response
def r_content_search():
    page = str(request.args.get('page', 1))
    page_size = str(request.args.get('page_size', 50))

    args_rules = [
        Rules.PAGE.value,
        Rules.PAGE_SIZE.value
    ]

    try:
        ji.Check.previewing(args_rules, {'page': page, 'page_size': page_size})
    except ji.PreviewingError, e:
        return json.loads(e.message)

    page = int(page)
    page_size = int(page_size)

    # 把page和page_size换算成offset和limit
    offset = (page - 1) * page_size
    # offset, limit将覆盖page及page_size的影响
    offset = str(request.args.get('offset', offset))
    limit = str(request.args.get('limit', page_size))

    order_by = request.args.get('order_by', 'id')
    order = request.args.get('order', 'asc')
    keyword = request.args.get('keyword', '')

    args_rules = [
        Rules.OFFSET.value,
        Rules.LIMIT.value,
        Rules.ORDER_BY.value,
        Rules.ORDER.value,
        Rules.KEYWORD.value
    ]

    try:
        ji.Check.previewing(args_rules, {'offset': offset, 'limit': limit, 'order_by': order_by, 'order': order,
                                         'keyword': keyword})
        offset = int(offset)
        limit = int(limit)
        ret = dict()
        ret['state'] = ji.Common.exchange_state(20000)
        ret['data'] = list()
        ret['paging'] = {'total': 0, 'offset': offset, 'limit': limit, 'page': page, 'page_size': page_size}

        ret['data'], ret['paging']['total'] = GuestDisk.content_search(offset=offset, limit=limit, order_by=order_by,
                                                                       order=order, keyword=keyword)

        host_url = request.host_url.rstrip('/')
        other_str = '&keyword=' + keyword + '&order=' + order + '&order_by=' + order_by
        last_pagination = (ret['paging']['total'] + page_size - 1) / page_size

        if page <= 1:
            ret['paging']['prev'] = host_url + blueprints.url_prefix + '/_search?page=1&page_size=' + \
                                    page_size.__str__() + other_str
        else:
            ret['paging']['prev'] = host_url + blueprints.url_prefix + '/_search?page=' + str(page-1) + \
                                    '&page_size=' + page_size.__str__() + other_str

        if page >= last_pagination:
            ret['paging']['next'] = host_url + blueprints.url_prefix + '/_search?page=' + last_pagination.__str__() + \
                                    '&page_size=' + page_size.__str__() + other_str
        else:
            ret['paging']['next'] = host_url + blueprints.url_prefix + '/_search?page=' + str(page+1) + \
                                    '&page_size=' + page_size.__str__() + other_str

        ret['paging']['first'] = host_url + blueprints.url_prefix + '/_search?page=1&page_size=' + \
            page_size.__str__() + other_str
        ret['paging']['last'] = \
            host_url + blueprints.url_prefix + '/_search?page=' + last_pagination.__str__() + '&page_size=' + \
            page_size.__str__() + other_str

        return ret
    except ji.PreviewingError, e:
        return json.loads(e.message)


@Utils.dumps2response
def r_update(uuid):

    args_rules = [
        Rules.UUID.value
    ]

    if 'label' in request.json:
        args_rules.append(
            Rules.LABEL.value,
        )

    if args_rules.__len__() < 2:
        ret = dict()
        ret['state'] = ji.Common.exchange_state(20000)
        return ret

    request.json['uuid'] = uuid

    try:
        ji.Check.previewing(args_rules, request.json)
        guest_disk = GuestDisk()
        guest_disk.uuid = uuid
        guest_disk.get_by('uuid')

        guest_disk.label = request.json.get('label', guest_disk.label)

        guest_disk.update()
        guest_disk.get()

        ret = dict()
        ret['state'] = ji.Common.exchange_state(20000)
        ret['data'] = guest_disk.__dict__
        return ret
    except ji.PreviewingError, e:
        return json.loads(e.message)

