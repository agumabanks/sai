<?php

namespace Tests\Feature;

use Tests\TestCase;

/**
 * VAL-CROSS-012: Health endpoint stable post-mission.
 *
 * This test verifies the backend health endpoint returns 200
 * with correct metadata after all changes.
 */
class BackendHealthTest extends TestCase
{
    /**
     * Verify the backend API health endpoint returns 200 with correct metadata.
     */
    public function test_backend_health_endpoint_returns_200(): void
    {
        $ch = curl_init('http://127.0.0.1:8101/api/health');
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 10,
            CURLOPT_CONNECTTIMEOUT => 5,
        ]);

        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error = curl_error($ch);
        curl_close($ch);

        $this->assertEmpty($error, "Health endpoint connection failed: {$error}");
        $this->assertEquals(200, $httpCode, "Health endpoint returned HTTP {$httpCode} instead of 200");

        $data = json_decode($response, true);
        $this->assertIsArray($data, 'Health endpoint should return valid JSON');
        $this->assertArrayHasKey('status', $data, 'Health response should contain "status" key');
        $this->assertEquals('ok', $data['status'], 'Health status should be "ok"');
        $this->assertArrayHasKey('service', $data, 'Health response should contain "service" key');
        $this->assertArrayHasKey('version', $data, 'Health response should contain "version" key');
    }
}
