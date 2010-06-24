# Copyright (C) 2010 AG Projects. See LICENSE for details.
#

"""Blink settings extensions."""

__all__ = ['SIPSimpleSettingsExtension']

from sipsimple.configuration import Setting, SettingsGroup, SettingsObjectExtension
from sipsimple.configuration.settings import AudioSettings

from blink.configuration.datatypes import ApplicationDataPath, SoundFile
from blink.resources import Resources


class AudioSettingsExtension(AudioSettings):
    recordings_directory = Setting(type=ApplicationDataPath, default=ApplicationDataPath('recordings'), nillable=False)


class SoundSettings(SettingsGroup):
    outbound_ringtone = Setting(type=SoundFile, default=SoundFile(Resources.get('sounds/ring_outbound.wav')), nillable=True)


class SIPSimpleSettingsExtension(SettingsObjectExtension):
    audio = AudioSettingsExtension
    sounds = SoundSettings


