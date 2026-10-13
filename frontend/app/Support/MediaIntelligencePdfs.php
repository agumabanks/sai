<?php

namespace App\Support;

use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\URL;
use Illuminate\Support\Str;

class MediaIntelligencePdfs
{
    public static function urlForBriefing(array $briefing): ?string
    {
        $filename = self::filenameForBriefing($briefing);

        if (! $filename || ! self::exists($filename)) {
            return null;
        }

        return route('media-intelligence.pdf', ['filename' => $filename]);
    }

    public static function temporarySignedUrlForBriefing(array $briefing, int $minutes = 1440): ?string
    {
        $filename = self::filenameForBriefing($briefing);

        if (! $filename || ! self::exists($filename)) {
            return null;
        }

        return URL::temporarySignedRoute(
            'media-intelligence.pdf',
            now()->addMinutes($minutes),
            ['filename' => $filename],
        );
    }

    public static function filenameForBriefing(array $briefing): ?string
    {
        $storedPath = (string) ($briefing['pdf_path'] ?? '');
        $storedFilename = self::safeFilename(basename($storedPath));

        if ($storedFilename && self::exists($storedFilename)) {
            return $storedFilename;
        }

        $createdAt = $briefing['created_at'] ?? null;
        if (! $createdAt) {
            return null;
        }

        try {
            return 'Sanaa_Media_News_'.Carbon::parse($createdAt)->format('Y_m_d').'.pdf';
        } catch (\Throwable) {
            return null;
        }
    }

    public static function pathForFilename(string $filename): ?string
    {
        $safeFilename = self::safeFilename($filename);

        if (! $safeFilename) {
            return null;
        }

        $path = dirname(base_path()).'/data/news/'.$safeFilename;

        return is_file($path) ? $path : null;
    }

    public static function exists(string $filename): bool
    {
        return self::pathForFilename($filename) !== null;
    }

    public static function safeFilename(string $filename): ?string
    {
        $filename = trim($filename);

        if ($filename === '' || ! Str::endsWith(Str::lower($filename), '.pdf')) {
            return null;
        }

        if (! preg_match('/\ASanaa_Media_[A-Za-z0-9_.-]+\.pdf\z/', $filename)) {
            return null;
        }

        return $filename;
    }
}
