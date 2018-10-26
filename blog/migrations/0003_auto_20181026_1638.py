# Generated by Django 2.1.2 on 2018-10-26 08:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0002_auto_20181011_1739'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImageLib',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(blank=True, default='', max_length=20, verbose_name='名称')),
                ('url', models.URLField(verbose_name='图片地址')),
            ],
            options={
                'verbose_name': '图库',
                'verbose_name_plural': '图库',
            },
        ),
        migrations.AddField(
            model_name='article',
            name='carousels',
            field=models.ManyToManyField(to='blog.ImageLib', verbose_name='轮播图库'),
        ),
    ]
