<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Yantrana\Components\Auth\Models\AuthModel;
use App\Yantrana\Components\Vendor\Models\VendorModel;
use App\Yantrana\Components\Vendor\Models\VendorSettingsModel;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Str;

class SokoSsoController extends Controller
{
    /**
     * Target path mapping for SSO redirects.
     * Maps friendly target names to WhatsJet vendor console paths.
     */
    protected array $targetPaths = [
        'dashboard'    => '/vendor-console',
        'chat'         => '/vendor-console/whatsapp',
        'bot-flows'    => '/vendor-console/bot-replies/bot-flows',
        'bot-replies'  => '/vendor-console/bot-replies',
        'settings'     => '/vendor-console/settings/general',
        'subscription' => '/vendor-console/subscription',
        'team'         => '/vendor-console/users',
        'templates'    => '/vendor-console/whatsapp/templates',
        'campaigns'    => '/vendor-console/whatsapp/campaign',
        'contacts'     => '/vendor-console/contacts',
        'groups'       => '/vendor-console/contacts/groups',
        'labels'       => '/vendor-console/contacts/labels',
        'account-setup'=> '/vendor-console/settings/whatsapp',
    ];

    /**
     * Generate a one-time SSO token for a Soko seller.
     *
     * POST /api/soko/sso-token
     * Body: { "seller_uuid": "...", "target": "chat" }
     * Auth: Bearer <provision_key>
     */
    public function generateToken(Request $request)
    {
        // Verify provision key
        $provisionKey = config('services.soko_provision_key');
        $bearerToken = $request->bearerToken();

        if (!$provisionKey || $bearerToken !== $provisionKey) {
            return response()->json(['success' => false, 'message' => 'Unauthorized'], 401);
        }

        $sellerUuid = $request->input('seller_uuid');
        $target = $request->input('target', 'dashboard');

        if (!$sellerUuid) {
            return response()->json(['success' => false, 'message' => 'seller_uuid is required'], 422);
        }

        // Find vendor by seller_uuid
        $vendorSetting = VendorSettingsModel::where('name', 'soko_seller_uuid')
            ->where('value', $sellerUuid)
            ->first();

        if (!$vendorSetting) {
            return response()->json(['success' => false, 'message' => 'Vendor not found for this seller'], 404);
        }

        $vendor = VendorModel::find($vendorSetting->vendors__id);
        if (!$vendor || $vendor->status != 1) {
            return response()->json(['success' => false, 'message' => 'Vendor inactive or not found'], 404);
        }

        // Find vendor admin user
        $admin = AuthModel::where('vendors__id', $vendor->_id)
            ->where('status', 1)
            ->first();

        if (!$admin) {
            return response()->json(['success' => false, 'message' => 'Vendor admin not found'], 404);
        }

        // Resolve redirect path
        $redirectPath = $this->targetPaths[$target] ?? $this->targetPaths['dashboard'];

        // Generate one-time token (60 seconds TTL)
        $token = Str::random(64);
        $cacheKey = "soko_sso:{$token}";

        Cache::put($cacheKey, [
            'admin_id' => $admin->_id,
            'vendor_id' => $vendor->_id,
            'redirect_path' => $redirectPath,
            'seller_uuid' => $sellerUuid,
        ], 60); // 60 seconds

        $loginUrl = url("/soko-sso/{$token}");

        return response()->json([
            'success' => true,
            'login_url' => $loginUrl,
            'expires_in' => 60,
        ]);
    }

    /**
     * Consume SSO token and log vendor admin in.
     *
     * GET /soko-sso/{token}
     */
    public function loginWithToken(string $token)
    {
        $cacheKey = "soko_sso:{$token}";

        // Atomic pull — token can only be used once
        $data = Cache::pull($cacheKey);

        if (!$data) {
            return redirect('/')->with('error', 'SSO link expired or already used.');
        }

        $admin = AuthModel::find($data['admin_id']);
        if (!$admin || $admin->status != 1) {
            return redirect('/')->with('error', 'Account is inactive.');
        }

        // Log the admin in using the web guard
        Auth::loginUsingId($admin->_id);

        // Regenerate session for security
        request()->session()->regenerate();

        return redirect($data['redirect_path']);
    }
}
