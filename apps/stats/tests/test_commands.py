import os
import shutil
from datetime import date, timedelta

from nose.tools import eq_

from django.conf import settings
from django.core import management

import amo.search
import amo.tests
# TODO: use DownloadCount and UpdateCount when the script is proven
# to work correctly.
from addons.models import Persona
from stats.models import (DownloadCountTmp as DownloadCount, ThemeUpdateCount,
                          UpdateCountTmp as UpdateCount)
from stats.management.commands.download_counts_from_file import is_valid_source
from zadmin.models import DownloadSource


hive_folder = os.path.join(settings.ROOT, 'apps/stats/fixtures/files')


class TestADICommand(amo.tests.TestCase):
    fixtures = ('base/addon_3615', 'base/featured', 'addons/persona')

    def setUp(self):
        self.clean_up_files()
        shutil.copytree(os.path.join(hive_folder, 'src'),
                        os.path.join(hive_folder, '2014-07-10'))

    def tearDown(self):
        self.clean_up_files()

    def clean_up_files(self):
        dirpath = os.path.join(hive_folder, '2014-07-10')
        if os.path.isdir(dirpath):
            for name in os.listdir(dirpath):
                os.unlink(os.path.join(dirpath, name))
            os.rmdir(dirpath)

    def test_update_counts_from_file(self):
        management.call_command('update_counts_from_file', hive_folder,
                                date='2014-07-10')
        eq_(UpdateCount.objects.all().count(), 1)
        update_count = UpdateCount.objects.last()
        eq_(update_count.count, 5)
        eq_(update_count.date, date(2014, 7, 10))
        eq_(update_count.versions, {u'3.8': 2, u'3.7': 3})
        eq_(update_count.statuses, {u'userEnabled': 5})
        eq_(update_count.applications, {u'{app-id}': {u'30.0': 18}})
        eq_(update_count.oses, {u'WINNT': 5})
        eq_(update_count.locales, {u'en_us': 5})

    def test_download_counts_from_file(self):
        # Create the necessary "valid download sources" entries.
        DownloadSource.objects.create(name='search', type='full')
        DownloadSource.objects.create(name='coll', type='prefix')

        management.call_command('download_counts_from_file', hive_folder,
                                date='2014-07-10')
        eq_(DownloadCount.objects.all().count(), 1)
        download_count = DownloadCount.objects.last()
        eq_(download_count.count, 2)
        eq_(download_count.date, date(2014, 7, 10))
        eq_(download_count.sources, {u'search': 1, u'collection': 1})

    def test_theme_update_counts_from_file(self):
        management.call_command('theme_update_counts_from_file', hive_folder,
                                date='2014-07-10')
        eq_(ThemeUpdateCount.objects.all().count(), 2)
        eq_(ThemeUpdateCount.objects.get(addon_id=3615).count, 2)
        # Persona 813 has addon id 15663: we need the count to be the sum of
        # the "old" request on the persona_id 813 (only the one with the source
        # "gp") and the "new" request on the addon_id 15663.
        eq_(ThemeUpdateCount.objects.get(addon_id=15663).count, 15)

    def test_update_theme_popularity_movers(self):
        # Create ThemeUpdateCount entries for the persona 559 with addon_id
        # 15663 and the persona 575 with addon_id 15679 for the last 28 days.
        # We start from the previous day, as the theme_update_counts_from_*
        # scripts are gathering data for the day before.
        yesterday = date.today() - timedelta(days=1)
        for i in range(28):
            d = yesterday - timedelta(days=i)
            ThemeUpdateCount.objects.create(addon_id=15663, count=i, date=d)
            ThemeUpdateCount.objects.create(addon_id=15679,
                                            count=i * 100, date=d)
        # Compute the popularity and movers.
        management.call_command('update_theme_popularity_movers')
        p1 = Persona.objects.get(pk=559)
        p2 = Persona.objects.get(pk=575)

        # TODO: remove _tmp from the fields when we use the ADI stuff for real
        # The popularity is the average over the last 7 days, and as we created
        # entries with one more user per day in the past (or 100 more), the
        # calculation is "sum(range(7)) / 7" (or "sum(range(7)) * 100 / 7").
        eq_(p1.popularity_tmp, 3)  # sum(range(7)) / 7
        eq_(p2.popularity_tmp, 300)  # sum(range(7)) * 100 / 7

        # Three weeks avg (sum(range(21)) / 21) = 10 so (3 - 10) / 10.
        # The movers is computed with the following formula:
        # previous_3_weeks: the average over the 21 days before the last 7 days
        # movers: (popularity - previous_3_weeks) / previous_3_weeks
        # The calculation for the previous_3_weeks is:
        # previous_3_weeks: (sum(range(28) - sum(range(7))) * 100 / 21 == 1700.
        eq_(p1.movers_tmp, 0.0)  # Because the popularity is <= 100.
        # We round the results to cope with floating point imprecision.
        eq_(round(p2.movers_tmp, 5), round((300.0 - 1700) / 1700, 5))

    def test_is_valid_source(self):
        assert is_valid_source('foo',
                               fulls=['foo', 'bar'],
                               prefixes=['baz', 'cruux'])
        assert not is_valid_source('foob',
                                   fulls=['foo', 'bar'],
                                   prefixes=['baz', 'cruux'])
        assert is_valid_source('foobaz',
                               fulls=['foo', 'bar'],
                               prefixes=['baz', 'cruux'])
        assert not is_valid_source('ba',
                                   fulls=['foo', 'bar'],
                                   prefixes=['baz', 'cruux'])
