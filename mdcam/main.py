import click
import datetime
import fnmatch
import logging
import os
import requests
import sys
import urllib

LOG = logging.getLogger(__name__)


class Settings(object):
    ipaddr = '192.168.1.1'
    port = 80
    user = 'admin'
    password = ''


@click.pass_context
def url_for(ctx, script):
    url = 'http://{addr}:{port}/{script}'.format(
        addr=ctx.obj.ipaddr, port=ctx.obj.port, script=script)

    LOG.debug('generated url "%s" for script "%s"',
              url, script)
    return url


@click.pass_context
def auth_params(ctx):
    return {'user': ctx.obj.user, 'pwd': ctx.obj.password}


@click.group()
@click.option('-i', '--ip', '--ipaddr',
              envvar='MDCAM_IPADDR',
              default='192.168.1.1')
@click.option('-p', '--port', default=80, type=int)
@click.option('-v', '--verbose', 'loglevel', flag_value='INFO')
@click.option('-d', '--debug', 'loglevel', flag_value='DEBUG')
@click.option('-u', '--user',
              envvar='MDCAM_USER',
              default='admin')
@click.option('-p', '--password',
              envvar='MDCAM_PASSWORD',
              default='')
@click.pass_context
def cli(ctx, ipaddr, port, user, password, loglevel='WARN'):
    ctx.obj = Settings()
    ctx.obj.ipaddr = ipaddr
    ctx.obj.port = port
    ctx.obj.user = user
    ctx.obj.password = password

    logging.basicConfig(level=loglevel)

    LOG.debug('using ipaddr %s, port %d', ctx.obj.ipaddr, ctx.obj.port)


@cli.command()
@click.option('--output', '-o')
def backup(output):
    if output is None:
        now = datetime.datetime.now()
        output = 'backup-{}.txt'.format(now.isoformat())

    res = requests.get(url_for('backup.cgi'),
                       params=dict(json=1, **auth_params()))

    res.raise_for_status()

    with open(output, 'w') as fd:
        fd.write(res.content)

    click.echo('Configured saved to {}'.format(output))


@cli.command()
@click.argument('paramfile')
def restore(paramfile):
    raise NotImplementedError('restore.cgi does not work as documented')
    with open(paramfile) as fd:
        paramdata = fd.read()

    res = requests.post(url_for('restore.cgi'),
                        data={'file': paramdata},
                        params=dict(json=1, **auth_params()))

    res.raise_for_status()

    click.echo('Configured restored.')

@cli.command()
@click.option('--output', '-o')
def snapshot(output):
    if output is None:
        now = datetime.datetime.now()
        output = 'snapshot-{}.jpg'.format(now.isoformat())

    res = requests.get(url_for('snapshot.cgi'),
                       params=dict(json=1, **auth_params()))

    res.raise_for_status()

    with open(output, 'w') as fd:
        fd.write(res.content)

    click.echo('Snapshot saved to {}'.format(output))


def show_kv_list(data, patterns, output):
    selected = set()
    for pattern in patterns:
        matched = (set(fnmatch.filter(data.keys(), pattern)))
        selected = selected.union(matched)

    selected = selected or data.keys()

    with open(output, 'w') if output else sys.stdout as fd:
        click.echo('\n'.join("{} = {}".format(k, data[k])
                             for k in sorted(selected)),
                   file=fd)

@cli.command()
@click.option('--output', '-o')
@click.argument('patterns', nargs=-1)
def get_params(output, patterns):
    res = requests.get(url_for('get_params.cgi'),
                       params=dict(json=1, **auth_params()))

    res.raise_for_status()
    show_kv_list(res.json(), patterns, output)


@cli.command()
@click.option('--output', '-o')
@click.argument('patterns', nargs=-1)
def get_status(output, patterns):
    res = requests.get(url_for('get_status.cgi'),
                       params=dict(json=1, **auth_params()))
    res.raise_for_status()
    show_kv_list(res.json(), patterns, output)


@cli.command()
@click.option('--output', '-o')
@click.argument('patterns', nargs=-1)
def get_properties(output, patterns):
    res = requests.get(url_for('get_properties.cgi'),
                       params=dict(json=1, **auth_params()))
    res.raise_for_status()
    show_kv_list(res.json(), patterns, output)


@cli.command()
@click.option('-n', '--nosave', is_flag=True)
@click.option('-r', '--reboot', is_flag=True)
@click.argument('pspec', nargs=-1)
def set_params(nosave, reboot, pspec):
    params = dict(x.split('=', 1) for x in pspec)
    params.update(auth_params())

    if not nosave:
        params['save'] = '1'

    if reboot:
        params['reboot'] = '1'

    res = requests.get(url_for('set_params.cgi'),
                       params=dict(**params))
    res.raise_for_status()

    click.echo('Configured.')


@cli.command()
def streamurl():
    url = url_for('av.asf')
    click.echo('{}?{}'.format(
        url, urllib.urlencode(auth_params())))


@cli.command()
def ls():
    res = requests.get(url_for('search_record.cgi'),
                       params=dict(json=1, **auth_params()))
    res.raise_for_status()
    data = res.json()

    if data['result'] < 0:
        raise RuntimeError('unable to list files ({result})'.format(**data))

    for rec in data['record']:
        click.echo('{path} {size}'.format(
            **rec
        ))


@cli.command()
@click.option('-o', '--output')
@click.argument('path')
def download(output, path):
    if output is None:
        output = os.path.basename(path)

    res = requests.get(url_for('get_record.cgi'),
                       params=dict(path=path, json=1, **auth_params()),
                       stream=True)

    res.raise_for_status()

    LOG.info('writing %s to %s', path, output)
    with open(output, 'w') as fd:
        for chunk in res.iter_content(chunk_size=8192):
            fd.write(chunk)


@cli.command()
@click.argument('name')
def rm(name):
    res = requests.get(url_for('del_record.cgi'),
                       params=dict(name=name, json=1, **auth_params()))
    res.raise_for_status()
    click.echo('Removed {}'.format(name))


@cli.command()
@click.option('-l', '--length')
def startrec(length):
    params = {'json': '1'}
    params.update(auth_params())

    if length is not None:
        params['length'] = length

    res = requests.get(url_for('start_record.cgi'),
                       params=dict(**params))
    res.raise_for_status()

    click.echo('Started recording task id {}'.format(res.json()['task']))


@cli.command()
@click.argument('task')
def stoprec(task):
    res = requests.get(url_for('stop_record.cgi'),
                       params=dict(task=task, json=1, **auth_params()))
    res.raise_for_status()

    click.echo('Stopped recording task id {}'.format(task))


@cli.command()
def log():
    res = requests.get(url_for('get_log.cgi'),
                       params=dict(json=1, **auth_params()))
    res.raise_for_status()

    data = res.json()
    for event in data['log']:
        if event.get('user'):
            click.echo('{user} from {ip} at {t}'.format(**event))


if __name__ == '__main__':
    cli()
