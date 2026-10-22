import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from app.detail_studio import evidence, render, sha, validate_plan

class DetailStudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        Image.new('RGB',(320,320),'#926737').save(self.source/'photo.png')
        self.data={'product_id':'p1','status':'complete','title':'테스트 상징 장식','assets':[{'file':'photo.png','sha256':sha(self.source/'photo.png'),'source_url':'https://example.com/photo.png','width':320,'height':320}]}
        (self.source/'detail.json').write_text(json.dumps(self.data))
        self.plan={'product_name':'상징 장식','positioning':'기획 시안','source_detail':str(self.source/'detail.json'),'source_sha256':sha(self.source/'detail.json'),'missing_before_publication':['거래 조건'],'cuts':[{'id':str(i),'family':'intro' if i==0 else 'key_points','headline':'마음을 담는 작은 상징','body':['일상에 의미를 더해보세요'],'asset_id':'source/photo.png','evidence_quote':'상징 장식','evidence_field':'title'} for i in range(6)]}
    def tearDown(self):self.temp.cleanup()
    def test_rejects_changed_source_asset(self):
        (self.source/'photo.png').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):evidence(self.source/'detail.json')
    def test_rejects_path_escape(self):
        self.data['assets'][0]['file']='../outside.png';(self.source/'detail.json').write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,'inside source'):evidence(self.source/'detail.json')
    def test_rejects_other_product_and_fake_quote(self):
        self.plan['cuts'][0]['asset_id']='other/photo.png'
        with self.assertRaisesRegex(ValueError,'Cross-product'):validate_plan(self.plan,self.data,['source/photo.png'])
        self.plan['cuts'][0]['asset_id']='source/photo.png';self.plan['cuts'][0]['evidence_quote']='없는 인증'
        with self.assertRaisesRegex(ValueError,'quote not found'):validate_plan(self.plan,self.data,['source/photo.png'])
    def test_rejects_unsupported_copy(self):
        self.plan['cuts'][0]['headline']='집중력 보장'
        with self.assertRaisesRegex(ValueError,'Unsupported'):validate_plan(self.plan,self.data,['source/photo.png'])
    def test_rejects_unsupported_numbers_and_changed_plan_source(self):
        self.plan['cuts'][0]['body']=['정확한 크기는 6.5cm입니다']
        with self.assertRaisesRegex(ValueError,'numeric claim'):validate_plan(self.plan,self.data,['source/photo.png'])
        self.plan['cuts'][0]['body']=['확인된 장식입니다']
        p=self.root/'plan.json';p.write_text(json.dumps(self.plan));self.data['title']='원본 변경';(self.source/'detail.json').write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,'source changed'):render(p,self.root/'out')
    def test_exports_real_images_animation_and_package(self):
        p=self.root/'plan.json';p.write_text(json.dumps(self.plan));out=self.root/'out';manifest=render(p,out)
        self.assertEqual(manifest['cuts'],6)
        with Image.open(out/'detail-full.png') as im:self.assertEqual(im.size,(860,7680))
        with Image.open(out/'intro.gif') as im:self.assertGreater(im.n_frames,1)
        for f in manifest['files']:self.assertEqual(sha(out/f['file']),f['sha256'])
        with zipfile.ZipFile(out/'detail-package.zip') as z:self.assertIsNone(z.testzip());self.assertIn('index.html',z.namelist())
