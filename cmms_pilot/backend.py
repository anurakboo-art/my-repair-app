"""Per-session Supabase client. Only publishable key + end-user JWT; never admin keys."""
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions


def client(url, key):
    return create_client(url, key, options=SyncClientOptions(auto_refresh_token=False, persist_session=False))


def restore(url, key, tokens):
    api = client(url, key)
    response = api.auth.set_session(tokens['access_token'], tokens['refresh_token'])
    user = api.auth.get_user().user  # Network validation, not locally trusted JWT metadata.
    session = response.session
    return api, user, {'access_token': session.access_token, 'refresh_token': session.refresh_token}


def command(api, action, data):
    return api.rpc('cmms_command', {'p_action': action, 'p_data': data}).execute().data


def records(api, table, **filters):
    rows = []
    identity = 'user_id' if table == 'cmms_members' else 'id'
    offset = 0
    while True:
        query = api.table(table).select('*').order(identity).range(offset, offset + 499)
        for key, value in filters.items():
            query = query.eq(key, value)
        batch = query.execute().data
        rows.extend(batch)
        if len(batch) < 500:
            return rows
        offset += 500


def upload_photo(api, job_id, upload):
    from io import BytesIO
    from uuid import uuid4
    from PIL import Image
    if upload.size > 5 * 1024 * 1024:
        raise ValueError('รูปต้องไม่เกิน 5 MB')
    data = upload.getvalue()
    with Image.open(BytesIO(data)) as image:
        if image.format not in ('PNG', 'JPEG') or image.width * image.height > 25000000:
            raise ValueError('รองรับเฉพาะ JPEG / PNG ไม่เกิน 25 ล้านพิกเซล')
        image.verify()
        kind = image.format
    ext, mime = ('png', 'image/png') if kind == 'PNG' else ('jpg', 'image/jpeg')
    path = f'{job_id}/{uuid4()}.{ext}'
    api.storage.from_('cmms-photos').upload(path, data, {'content-type': mime, 'upsert': 'false'})
    return path

