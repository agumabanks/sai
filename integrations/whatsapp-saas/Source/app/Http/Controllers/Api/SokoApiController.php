<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Yantrana\Components\Contact\Models\ContactGroupModel;
use App\Yantrana\Components\Contact\Models\ContactModel;
use App\Yantrana\Components\Contact\Models\LabelModel;
use App\Yantrana\Components\Contact\Models\ContactLabelModel;
use App\Yantrana\Components\Contact\Models\ContactCustomFieldModel;
use App\Yantrana\Components\BotReply\Models\BotReplyModel;
use App\Yantrana\Components\Campaign\Models\CampaignModel;
use App\Yantrana\Components\WhatsAppService\Models\WhatsAppMessageLogModel;
use App\Yantrana\Components\Vendor\Models\VendorModel;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

class SokoApiController extends Controller
{
    /**
     * Get the authenticated vendor's internal ID.
     */
    protected function vendorId(): int
    {
        return Auth::user()->vendors__id;
    }

    // ═══════════════════════════════════════════════════════════════════
    // CONTACT GROUPS
    // ═══════════════════════════════════════════════════════════════════

    public function contactGroups(Request $request)
    {
        $groups = ContactGroupModel::where('vendors__id', $this->vendorId())
            ->where('status', 1)
            ->orderBy('title')
            ->get(['_id', '_uid', 'title', 'description', 'status', 'created_at']);

        // Add contact count per group
        $groups->each(function ($group) {
            $group->contact_count = DB::table('group_contacts')
                ->where('contact_groups__id', $group->_id)
                ->count();
        });

        return response()->json(['success' => true, 'data' => $groups]);
    }

    public function createContactGroup(Request $request)
    {
        $request->validate([
            'title' => 'required|string|max:150',
            'description' => 'nullable|string|max:500',
        ]);

        $group = new ContactGroupModel();
        $group->_uid = (string) Str::uuid();
        $group->title = $request->input('title');
        $group->description = $request->input('description');
        $group->vendors__id = $this->vendorId();
        $group->status = 1;
        $group->save();

        return response()->json(['success' => true, 'data' => $group, 'message' => 'Group created']);
    }

    public function updateContactGroup(Request $request, $vendorUid, $groupUid)
    {
        $request->validate([
            'title' => 'required|string|max:150',
            'description' => 'nullable|string|max:500',
        ]);

        $group = ContactGroupModel::where('_uid', $groupUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $group->title = $request->input('title');
        $group->description = $request->input('description');
        $group->save();

        return response()->json(['success' => true, 'data' => $group, 'message' => 'Group updated']);
    }

    public function deleteContactGroup(Request $request, $vendorUid, $groupUid)
    {
        $group = ContactGroupModel::where('_uid', $groupUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        // Remove contact associations
        DB::table('group_contacts')
            ->where('contact_groups__id', $group->_id)
            ->delete();

        $group->delete();

        return response()->json(['success' => true, 'message' => 'Group deleted']);
    }

    public function assignContactGroups(Request $request, $vendorUid, $contactUid)
    {
        $request->validate([
            'group_uids' => 'required|array',
            'group_uids.*' => 'string',
        ]);

        $contact = ContactModel::where('_uid', $contactUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $groupIds = ContactGroupModel::where('vendors__id', $this->vendorId())
            ->whereIn('_uid', $request->input('group_uids'))
            ->pluck('_id');

        // Sync — remove old, add new
        DB::table('group_contacts')
            ->where('contacts__id', $contact->_id)
            ->delete();

        foreach ($groupIds as $groupId) {
            DB::table('group_contacts')->insert([
                'contact_groups__id' => $groupId,
                'contacts__id' => $contact->_id,
            ]);
        }

        return response()->json(['success' => true, 'message' => 'Groups assigned', 'count' => $groupIds->count()]);
    }

    // ═══════════════════════════════════════════════════════════════════
    // CONTACT LABELS
    // ═══════════════════════════════════════════════════════════════════

    public function contactLabels(Request $request)
    {
        $labels = LabelModel::where('vendors__id', $this->vendorId())
            ->where('status', 1)
            ->orderBy('title')
            ->get(['_id', '_uid', 'title', 'text_color', 'bg_color', 'created_at']);

        return response()->json(['success' => true, 'data' => $labels]);
    }

    public function createContactLabel(Request $request)
    {
        $request->validate([
            'title' => 'required|string|max:100',
            'text_color' => 'nullable|string|max:20',
            'bg_color' => 'nullable|string|max:20',
        ]);

        $label = new LabelModel();
        $label->_uid = (string) Str::uuid();
        $label->title = $request->input('title');
        $label->text_color = $request->input('text_color', '#ffffff');
        $label->bg_color = $request->input('bg_color', '#3b82f6');
        $label->vendors__id = $this->vendorId();
        $label->status = 1;
        $label->save();

        return response()->json(['success' => true, 'data' => $label, 'message' => 'Label created']);
    }

    public function updateContactLabel(Request $request, $vendorUid, $labelUid)
    {
        $request->validate([
            'title' => 'required|string|max:100',
            'text_color' => 'nullable|string|max:20',
            'bg_color' => 'nullable|string|max:20',
        ]);

        $label = LabelModel::where('_uid', $labelUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $label->title = $request->input('title');
        if ($request->has('text_color')) $label->text_color = $request->input('text_color');
        if ($request->has('bg_color')) $label->bg_color = $request->input('bg_color');
        $label->save();

        return response()->json(['success' => true, 'data' => $label, 'message' => 'Label updated']);
    }

    public function deleteContactLabel(Request $request, $vendorUid, $labelUid)
    {
        $label = LabelModel::where('_uid', $labelUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        // Remove contact associations
        ContactLabelModel::where('labels__id', $label->_id)->delete();
        $label->delete();

        return response()->json(['success' => true, 'message' => 'Label deleted']);
    }

    public function assignContactLabels(Request $request, $vendorUid, $contactUid)
    {
        $request->validate([
            'label_uids' => 'required|array',
            'label_uids.*' => 'string',
        ]);

        $contact = ContactModel::where('_uid', $contactUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $labelIds = LabelModel::where('vendors__id', $this->vendorId())
            ->whereIn('_uid', $request->input('label_uids'))
            ->pluck('_id');

        // Sync
        ContactLabelModel::where('contacts__id', $contact->_id)->delete();

        foreach ($labelIds as $labelId) {
            $cl = new ContactLabelModel();
            $cl->_uid = (string) Str::uuid();
            $cl->labels__id = $labelId;
            $cl->contacts__id = $contact->_id;
            $cl->status = 1;
            $cl->save();
        }

        return response()->json(['success' => true, 'message' => 'Labels assigned', 'count' => $labelIds->count()]);
    }

    // ═══════════════════════════════════════════════════════════════════
    // CONTACT OPERATIONS
    // ═══════════════════════════════════════════════════════════════════

    public function blockContact(Request $request, $vendorUid, $contactUid)
    {
        $contact = ContactModel::where('_uid', $contactUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $contact->status = 5; // blocked status
        $contact->save();

        return response()->json(['success' => true, 'message' => 'Contact blocked']);
    }

    public function unblockContact(Request $request, $vendorUid, $contactUid)
    {
        $contact = ContactModel::where('_uid', $contactUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $contact->status = 1; // active status
        $contact->save();

        return response()->json(['success' => true, 'message' => 'Contact unblocked']);
    }

    public function toggleAiBot(Request $request, $vendorUid, $contactUid)
    {
        $contact = ContactModel::where('_uid', $contactUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $contact->disable_ai_bot = $contact->disable_ai_bot ? 0 : 1;
        $contact->save();

        return response()->json([
            'success' => true,
            'ai_bot_enabled' => !$contact->disable_ai_bot,
            'message' => $contact->disable_ai_bot ? 'AI bot disabled for contact' : 'AI bot enabled for contact',
        ]);
    }

    public function exportContacts(Request $request, $vendorUid, $type = 'csv')
    {
        $contacts = ContactModel::where('vendors__id', $this->vendorId())
            ->where('status', 1)
            ->select('first_name', 'last_name', 'wa_id', 'email', 'language_code', 'created_at')
            ->get();

        if ($type === 'json') {
            return response()->json(['success' => true, 'data' => $contacts]);
        }

        // CSV export
        $csv = "First Name,Last Name,Phone,Email,Language,Created At\n";
        foreach ($contacts as $c) {
            $csv .= "\"{$c->first_name}\",\"{$c->last_name}\",\"{$c->wa_id}\",\"{$c->email}\",\"{$c->language_code}\",\"{$c->created_at}\"\n";
        }

        return response($csv, 200, [
            'Content-Type' => 'text/csv',
            'Content-Disposition' => 'attachment; filename="contacts_' . date('Y-m-d') . '.csv"',
        ]);
    }

    // ═══════════════════════════════════════════════════════════════════
    // CONTACT CUSTOM FIELDS
    // ═══════════════════════════════════════════════════════════════════

    public function contactCustomFields(Request $request)
    {
        $fields = ContactCustomFieldModel::where('vendors__id', $this->vendorId())
            ->where('status', 1)
            ->orderBy('input_name')
            ->get(['_id', '_uid', 'input_name', 'input_type', 'created_at']);

        return response()->json(['success' => true, 'data' => $fields]);
    }

    public function createContactCustomField(Request $request)
    {
        $request->validate([
            'input_name' => 'required|string|max:100',
            'input_type' => 'required|in:text,number,date,url,textarea',
        ]);

        $field = new ContactCustomFieldModel();
        $field->_uid = (string) Str::uuid();
        $field->input_name = $request->input('input_name');
        $field->input_type = $request->input('input_type');
        $field->vendors__id = $this->vendorId();
        $field->status = 1;
        $field->save();

        return response()->json(['success' => true, 'data' => $field, 'message' => 'Custom field created']);
    }

    public function deleteContactCustomField(Request $request, $vendorUid, $fieldUid)
    {
        $field = ContactCustomFieldModel::where('_uid', $fieldUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $field->delete();

        return response()->json(['success' => true, 'message' => 'Custom field deleted']);
    }

    // ═══════════════════════════════════════════════════════════════════
    // CHAT / INBOX
    // ═══════════════════════════════════════════════════════════════════

    public function chatContacts(Request $request)
    {
        $vendorId = $this->vendorId();
        $search = $request->input('search');
        $limit = min((int) $request->input('limit', 50), 100);

        $query = ContactModel::where('contacts.vendors__id', $vendorId)
            ->where('contacts.status', 1)
            ->leftJoin('whatsapp_message_logs as last_msg', function ($join) use ($vendorId) {
                $join->on('last_msg.contacts__id', '=', 'contacts._id')
                    ->where('last_msg.vendors__id', $vendorId)
                    ->whereRaw('last_msg._id = (SELECT MAX(wml._id) FROM whatsapp_message_logs wml WHERE wml.contacts__id = contacts._id AND wml.vendors__id = ?)', [$vendorId]);
            })
            ->select(
                'contacts._uid',
                'contacts.first_name',
                'contacts.last_name',
                'contacts.wa_id',
                'contacts.email',
                'contacts.disable_ai_bot',
                'last_msg.message as last_message',
                'last_msg.is_incoming_message as last_msg_incoming',
                'last_msg.messaged_at as last_message_at',
                'last_msg.status as last_message_status'
            );

        if ($search) {
            $query->where(function ($q) use ($search) {
                $q->where('contacts.first_name', 'like', "%{$search}%")
                  ->orWhere('contacts.last_name', 'like', "%{$search}%")
                  ->orWhere('contacts.wa_id', 'like', "%{$search}%");
            });
        }

        $contacts = $query->orderByDesc('last_msg.messaged_at')
            ->limit($limit)
            ->get();

        // Unread counts
        $contacts->each(function ($contact) use ($vendorId) {
            $contactId = ContactModel::where('_uid', $contact->_uid)->value('_id');
            $contact->unread_count = WhatsAppMessageLogModel::where('vendors__id', $vendorId)
                ->where('contacts__id', $contactId)
                ->where('is_incoming_message', 1)
                ->where('status', 'received')
                ->count();
        });

        return response()->json(['success' => true, 'data' => $contacts]);
    }

    public function chatMessages(Request $request, $vendorUid, $contactUid)
    {
        $vendorId = $this->vendorId();
        $limit = min((int) $request->input('limit', 50), 200);
        $before = $request->input('before'); // pagination cursor

        $contact = ContactModel::where('_uid', $contactUid)
            ->where('vendors__id', $vendorId)
            ->firstOrFail();

        $query = WhatsAppMessageLogModel::where('vendors__id', $vendorId)
            ->where('contacts__id', $contact->_id)
            ->select('_uid', 'message', 'status', 'is_incoming_message', 'messaged_at', 'wamid', '__data', 'created_at');

        if ($before) {
            $query->where('_id', '<', $before);
        }

        $messages = $query->orderByDesc('_id')
            ->limit($limit)
            ->get();

        // Parse media from __data
        $messages->each(function ($msg) {
            $data = is_string($msg->__data) ? json_decode($msg->__data, true) : $msg->__data;
            $msg->media = $data['media'] ?? null;
            $msg->message_type = isset($data['media']['type']) ? $data['media']['type'] : 'text';
            unset($msg->__data);
        });

        // Mark incoming as read
        WhatsAppMessageLogModel::where('vendors__id', $vendorId)
            ->where('contacts__id', $contact->_id)
            ->where('is_incoming_message', 1)
            ->where('status', 'received')
            ->update(['status' => 'read']);

        return response()->json([
            'success' => true,
            'data' => $messages,
            'contact' => [
                'uid' => $contact->_uid,
                'name' => trim($contact->first_name . ' ' . $contact->last_name),
                'phone' => $contact->wa_id,
            ],
        ]);
    }

    public function chatSend(Request $request, $vendorUid, $contactUid)
    {
        // This delegates to the existing apiSendChatMessage flow
        // The Soko proxy should call the existing /contact/send-message endpoint
        return response()->json([
            'success' => false,
            'message' => 'Use POST /{vendorUid}/contact/send-message instead.',
        ], 400);
    }

    public function chatSendMedia(Request $request, $vendorUid, $contactUid)
    {
        return response()->json([
            'success' => false,
            'message' => 'Use POST /{vendorUid}/contact/send-media-message instead.',
        ], 400);
    }

    public function unreadCount(Request $request)
    {
        $count = WhatsAppMessageLogModel::where('vendors__id', $this->vendorId())
            ->where('is_incoming_message', 1)
            ->where('status', 'received')
            ->count();

        return response()->json(['success' => true, 'unread_count' => $count]);
    }

    // ═══════════════════════════════════════════════════════════════════
    // MESSAGE LOG
    // ═══════════════════════════════════════════════════════════════════

    public function messageLog(Request $request)
    {
        $vendorId = $this->vendorId();
        $startDate = $request->input('start_date');
        $endDate = $request->input('end_date');
        $type = $request->input('type'); // incoming, outgoing
        $limit = min((int) $request->input('limit', 50), 200);
        $page = max((int) $request->input('page', 1), 1);

        $query = WhatsAppMessageLogModel::where('whatsapp_message_logs.vendors__id', $vendorId)
            ->join('contacts', 'contacts._id', '=', 'whatsapp_message_logs.contacts__id')
            ->select(
                'whatsapp_message_logs._uid',
                'whatsapp_message_logs.message',
                'whatsapp_message_logs.status',
                'whatsapp_message_logs.is_incoming_message',
                'whatsapp_message_logs.messaged_at',
                'whatsapp_message_logs.contact_wa_id',
                'contacts.first_name',
                'contacts.last_name'
            );

        if ($startDate) {
            $query->where('whatsapp_message_logs.messaged_at', '>=', $startDate);
        }
        if ($endDate) {
            $query->where('whatsapp_message_logs.messaged_at', '<=', $endDate . ' 23:59:59');
        }
        if ($type === 'incoming') {
            $query->where('whatsapp_message_logs.is_incoming_message', 1);
        } elseif ($type === 'outgoing') {
            $query->where('whatsapp_message_logs.is_incoming_message', 0);
        }

        $total = (clone $query)->count();
        $messages = $query->orderByDesc('whatsapp_message_logs.messaged_at')
            ->offset(($page - 1) * $limit)
            ->limit($limit)
            ->get();

        return response()->json([
            'success' => true,
            'data' => $messages,
            'pagination' => [
                'total' => $total,
                'page' => $page,
                'limit' => $limit,
                'pages' => ceil($total / $limit),
            ],
        ]);
    }

    public function messageLogDetail(Request $request, $vendorUid, $messageUid)
    {
        $message = WhatsAppMessageLogModel::where('_uid', $messageUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $contact = ContactModel::find($message->contacts__id);

        $data = is_string($message->__data) ? json_decode($message->__data, true) : ($message->__data ?? []);

        return response()->json([
            'success' => true,
            'data' => [
                'uid' => $message->_uid,
                'message' => $message->message,
                'status' => $message->status,
                'is_incoming' => (bool) $message->is_incoming_message,
                'messaged_at' => $message->messaged_at,
                'wamid' => $message->wamid,
                'media' => $data['media'] ?? null,
                'contact' => $contact ? [
                    'uid' => $contact->_uid,
                    'name' => trim($contact->first_name . ' ' . $contact->last_name),
                    'phone' => $contact->wa_id,
                ] : null,
            ],
        ]);
    }

    // ═══════════════════════════════════════════════════════════════════
    // BOT REPLIES
    // ═══════════════════════════════════════════════════════════════════

    public function botReplies(Request $request)
    {
        $bots = BotReplyModel::where('vendors__id', $this->vendorId())
            ->where('status', '!=', 5) // not deleted
            ->orderBy('priority_index')
            ->get(['_id', '_uid', 'name', 'reply_text', 'trigger_type', 'reply_trigger', 'priority_index', 'status', 'created_at']);

        return response()->json(['success' => true, 'data' => $bots]);
    }

    public function botReplyDetail(Request $request, $vendorUid, $botReplyUid)
    {
        $bot = BotReplyModel::where('_uid', $botReplyUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $data = is_string($bot->__data) ? json_decode($bot->__data, true) : ($bot->__data ?? []);

        return response()->json([
            'success' => true,
            'data' => [
                'uid' => $bot->_uid,
                'name' => $bot->name,
                'reply_text' => $bot->reply_text,
                'trigger_type' => $bot->trigger_type,
                'reply_trigger' => $bot->reply_trigger,
                'priority_index' => $bot->priority_index,
                'status' => $bot->status,
                'media' => $data['media'] ?? null,
                'header' => $data['header_text'] ?? null,
                'footer' => $data['footer_text'] ?? null,
                'buttons' => $data['interactive_buttons'] ?? null,
            ],
        ]);
    }

    public function createBotReply(Request $request)
    {
        $request->validate([
            'name' => 'required|string|max:150',
            'reply_text' => 'required|string|max:4096',
            'trigger_type' => 'required|in:exact,contains,starts_with',
            'reply_trigger' => 'required|string|max:500',
        ]);

        $bot = new BotReplyModel();
        $bot->_uid = (string) Str::uuid();
        $bot->name = $request->input('name');
        $bot->reply_text = $request->input('reply_text');
        $bot->trigger_type = $request->input('trigger_type', 'contains');
        $bot->reply_trigger = $request->input('reply_trigger');
        $bot->priority_index = $request->input('priority_index', 0);
        $bot->vendors__id = $this->vendorId();
        $bot->status = 1;
        $bot->__data = json_encode([
            'header_text' => $request->input('header_text'),
            'footer_text' => $request->input('footer_text'),
        ]);
        $bot->save();

        return response()->json(['success' => true, 'data' => $bot, 'message' => 'Bot reply created']);
    }

    public function updateBotReply(Request $request, $vendorUid, $botReplyUid)
    {
        $request->validate([
            'name' => 'sometimes|string|max:150',
            'reply_text' => 'sometimes|string|max:4096',
            'trigger_type' => 'sometimes|in:exact,contains,starts_with',
            'reply_trigger' => 'sometimes|string|max:500',
        ]);

        $bot = BotReplyModel::where('_uid', $botReplyUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        if ($request->has('name')) $bot->name = $request->input('name');
        if ($request->has('reply_text')) $bot->reply_text = $request->input('reply_text');
        if ($request->has('trigger_type')) $bot->trigger_type = $request->input('trigger_type');
        if ($request->has('reply_trigger')) $bot->reply_trigger = $request->input('reply_trigger');
        if ($request->has('priority_index')) $bot->priority_index = $request->input('priority_index');
        if ($request->has('status')) $bot->status = $request->input('status');

        $data = is_string($bot->__data) ? json_decode($bot->__data, true) : ($bot->__data ?? []);
        if ($request->has('header_text')) $data['header_text'] = $request->input('header_text');
        if ($request->has('footer_text')) $data['footer_text'] = $request->input('footer_text');
        $bot->__data = json_encode($data);

        $bot->save();

        return response()->json(['success' => true, 'data' => $bot, 'message' => 'Bot reply updated']);
    }

    public function deleteBotReply(Request $request, $vendorUid, $botReplyUid)
    {
        $bot = BotReplyModel::where('_uid', $botReplyUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $bot->status = 5; // soft delete
        $bot->save();

        return response()->json(['success' => true, 'message' => 'Bot reply deleted']);
    }

    // ═══════════════════════════════════════════════════════════════════
    // CAMPAIGNS
    // ═══════════════════════════════════════════════════════════════════

    public function campaigns(Request $request)
    {
        $vendorId = $this->vendorId();
        $status = $request->input('status');
        $limit = min((int) $request->input('limit', 50), 100);
        $page = max((int) $request->input('page', 1), 1);

        $query = CampaignModel::where('vendors__id', $vendorId);

        if ($status) {
            $statusMap = ['active' => 1, 'archived' => 5, 'completed' => 2, 'scheduled' => 3];
            if (isset($statusMap[$status])) {
                $query->where('status', $statusMap[$status]);
            }
        }

        $total = (clone $query)->count();
        $campaigns = $query->orderByDesc('created_at')
            ->offset(($page - 1) * $limit)
            ->limit($limit)
            ->get(['_id', '_uid', 'title', 'template_name', 'template_language', 'scheduled_at', 'status', 'created_at', '__data']);

        $campaigns->each(function ($c) use ($vendorId) {
            $data = is_string($c->__data) ? json_decode($c->__data, true) : ($c->__data ?? []);
            $c->total_contacts = DB::table('whatsapp_message_queue')
                ->where('campaigns__id', $c->_id)
                ->count();
            $c->sent_count = DB::table('whatsapp_message_queue')
                ->where('campaigns__id', $c->_id)
                ->where('status', 2)
                ->count();
            $c->failed_count = DB::table('whatsapp_message_queue')
                ->where('campaigns__id', $c->_id)
                ->where('status', 3)
                ->count();
            unset($c->__data);
        });

        return response()->json([
            'success' => true,
            'data' => $campaigns,
            'pagination' => [
                'total' => $total,
                'page' => $page,
                'limit' => $limit,
            ],
        ]);
    }

    public function campaignStatus(Request $request, $vendorUid, $campaignUid)
    {
        $campaign = CampaignModel::where('_uid', $campaignUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $statusCounts = DB::table('whatsapp_message_queue')
            ->where('campaigns__id', $campaign->_id)
            ->selectRaw("
                COUNT(*) as total,
                SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as queued,
                SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN status = 3 THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 4 THEN 1 ELSE 0 END) as expired
            ")
            ->first();

        return response()->json([
            'success' => true,
            'data' => [
                'uid' => $campaign->_uid,
                'title' => $campaign->title,
                'status' => $campaign->status,
                'scheduled_at' => $campaign->scheduled_at,
                'stats' => $statusCounts,
            ],
        ]);
    }

    public function campaignExecutedLog(Request $request, $vendorUid, $campaignUid)
    {
        $campaign = CampaignModel::where('_uid', $campaignUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $limit = min((int) $request->input('limit', 50), 200);
        $page = max((int) $request->input('page', 1), 1);

        $logs = DB::table('whatsapp_message_queue')
            ->where('campaigns__id', $campaign->_id)
            ->leftJoin('contacts', 'contacts._id', '=', 'whatsapp_message_queue.contacts__id')
            ->select(
                'whatsapp_message_queue._uid',
                'whatsapp_message_queue.status',
                'whatsapp_message_queue.created_at',
                'whatsapp_message_queue.updated_at',
                'contacts.first_name',
                'contacts.last_name',
                'contacts.wa_id'
            )
            ->orderByDesc('whatsapp_message_queue.updated_at')
            ->offset(($page - 1) * $limit)
            ->limit($limit)
            ->get();

        return response()->json([
            'success' => true,
            'data' => $logs,
        ]);
    }

    public function archiveCampaign(Request $request, $vendorUid, $campaignUid)
    {
        $campaign = CampaignModel::where('_uid', $campaignUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $campaign->status = 5; // archived
        $campaign->save();

        return response()->json(['success' => true, 'message' => 'Campaign archived']);
    }

    public function unarchiveCampaign(Request $request, $vendorUid, $campaignUid)
    {
        $campaign = CampaignModel::where('_uid', $campaignUid)
            ->where('vendors__id', $this->vendorId())
            ->firstOrFail();

        $campaign->status = 1; // active
        $campaign->save();

        return response()->json(['success' => true, 'message' => 'Campaign unarchived']);
    }

    // ═══════════════════════════════════════════════════════════════════
    // HSM TEMPLATES (Meta WhatsApp Templates)
    // ═══════════════════════════════════════════════════════════════════

    public function templates(Request $request)
    {
        $templates = DB::table('whatsapp_templates')
            ->where('vendors__id', $this->vendorId())
            ->orderBy('template_name')
            ->get(['_uid', 'template_name', 'language', 'category', 'status', 'created_at', '__data']);

        $templates->each(function ($t) {
            $data = is_string($t->__data) ? json_decode($t->__data, true) : ($t->__data ?? []);
            $t->components = $data['components'] ?? [];
            unset($t->__data);
        });

        return response()->json(['success' => true, 'data' => $templates]);
    }

    public function syncTemplates(Request $request)
    {
        // Trigger template sync from Meta — this calls the WhatsApp API
        // We delegate to the existing engine
        try {
            $engine = app(\App\Yantrana\Components\WhatsAppService\WhatsAppTemplateEngine::class);
            $result = $engine->processSyncTemplates();
            return response()->json([
                'success' => $result->success(),
                'message' => $result->success() ? 'Templates synced' : 'Sync failed',
            ]);
        } catch (\Exception $e) {
            return response()->json(['success' => false, 'message' => $e->getMessage()], 500);
        }
    }

    public function createTemplate(Request $request)
    {
        // Template creation goes through Meta API — redirect to SSO for now
        return response()->json([
            'success' => false,
            'message' => 'Template creation requires Meta Business Manager. Use SSO to access the templates page.',
            'sso_target' => 'templates',
        ], 400);
    }

    // ═══════════════════════════════════════════════════════════════════
    // DASHBOARD STATS
    // ═══════════════════════════════════════════════════════════════════

    public function dashboardStats(Request $request)
    {
        $vendorId = $this->vendorId();
        $startDate = $request->input('start_date', now()->subDays(30)->toDateString());
        $endDate = $request->input('end_date', now()->toDateString());

        // Use raw DB queries to avoid Eloquent model serialization issues
        $messageStats = DB::table('whatsapp_message_logs')
            ->where('vendors__id', $vendorId)
            ->whereBetween('messaged_at', [$startDate, $endDate . ' 23:59:59'])
            ->selectRaw("
                COUNT(*) as total_messages,
                SUM(CASE WHEN is_incoming_message = 1 THEN 1 ELSE 0 END) as incoming,
                SUM(CASE WHEN is_incoming_message = 0 THEN 1 ELSE 0 END) as outgoing,
                SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) as delivered,
                SUM(CASE WHEN status = 'read' THEN 1 ELSE 0 END) as `read_count`,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            ")
            ->first();

        $contactStats = DB::table('contacts')
            ->where('vendors__id', $vendorId)
            ->selectRaw("
                COUNT(*) as total_contacts,
                SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN status = 5 THEN 1 ELSE 0 END) as blocked
            ")
            ->first();

        $campaignStats = DB::table('campaigns')
            ->where('vendors__id', $vendorId)
            ->selectRaw("
                COUNT(*) as total_campaigns,
                SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) as completed
            ")
            ->first();

        $botCount = DB::table('bot_replies')
            ->where('vendors__id', $vendorId)
            ->where('status', 1)
            ->count();

        return response()->json([
            'success' => true,
            'data' => [
                'period' => ['start' => $startDate, 'end' => $endDate],
                'messages' => $messageStats,
                'contacts' => $contactStats,
                'campaigns' => $campaignStats,
                'active_bot_replies' => $botCount,
            ],
        ]);
    }
}
