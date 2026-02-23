<!-- Contact Filter Form -->
<x-lw.modal id="lwContactFilter" :header="__tr('Advanced Filter')" :hasForm="true">
    <div id="lwContactFilterBody" class="lw-form-modal-body"></div>
    <script type="text/template" id="lwContactFilterBody-template">                    
        <x-lw.form id="lwContactFilterForm" :action="route('vendor.contact.write.store_contact_filter')"
            :data-callback-params="['modalId' => '#lwContactFilter', 'datatableId' => '#lwContactList']"
            data-callback="appFuncs.modelSuccessCallback">
            <!-- form body -->
            <div class="lw-form-modal-body">
                <fieldset>
                    <legend>{{  __tr('Basic Info') }}</legend>  
                    <div class="mb-3 row">
                        <label for="lwFirstNameField" class="col-sm-2 col-form-label">{{ __tr('First Name') }}</label>
                        <div class="col-sm-10">
                            <input name="first_name" class="form-control" id="lwFirstNameField" value="<%= __tData?.filterData?.first_name %>">
                        </div>
                    </div>
                    <div class="mb-3 row">
                        <label for="lwLastNameField" class="col-sm-2 col-form-label">{{ __tr('Last Name') }}</label>
                        <div class="col-sm-10">
                            <input type="text" name="last_name" class="form-control" id="lwLastNameField" value="<%= __tData?.filterData?.last_name %>">
                        </div>
                    </div>
                    <div class="mb-3 row">
                        <label for="lwCountryField" class="col-sm-2 col-form-label">{{ __tr('Country') }}</label>
                        <div class="col-sm-10">
                            <x-lw.input-field type="selectize" data-lw-plugin="lwSelectize" id="lwCountryField"
                                class="lw-contact-filter-selectize" name="countries_id[]" data-selected="[<%= __tData?.filterData?.countries_id %>]" multiple>
                                <x-slot name="selectOptions">
                                    <option value="">{{ __tr('Country') }}</option>
                                    @foreach(getCountryPhoneCodes() as $getCountryCode)
                                    <option value="{{ $getCountryCode['_id'] }}">{{ $getCountryCode['name'] }}</option>
                                    @endforeach
                                </x-slot>
                            </x-lw.input-field>
                        </div>
                    </div>
                    <div class="mb-3 row">
                        <label for="lwMobileNumberField" class="col-sm-2 col-form-label">{{ __tr('Mobile Number') }}</label>
                        <div class="col-sm-10">
                            <input type="text" name="wa_id" class="form-control" id="lwMobileNumberField" value="<%= __tData?.filterData?.wa_id %>">
                        </div>
                    </div>
                    <div class="mb-3 row">
                        <label for="lwLanguageField" class="col-sm-2 col-form-label">{{ __tr('Language') }}</label>
                        <div class="col-sm-10">
                            <?php $languages = include app_path('Yantrana/Support/languages.php'); ?>
                            <x-lw.input-field type="selectize" data-lw-plugin="lwSelectize" id="lwLanguageField"
                                class="lw-contact-filter-selectize" name="language_codes[]" data-selected="[<%= __tData?.filterData?.language_codes %>]" multiple>
                                <x-slot name="selectOptions">
                                    <option value="">{{ __tr('Select Language') }}</option>
                                    @foreach($languages as $key => $language)
                                    <option value="{{ $key }}">{{ $language['language'] }}</option>
                                    @endforeach
                                </x-slot>
                            </x-lw.input-field>
                        </div>
                    </div>
                    <div class="mb-3 row">
                        <label for="lwEmailField" class="col-sm-2 col-form-label">{{ __tr('Email') }}</label>
                        <div class="col-sm-10">
                            <input type="email" name="email" class="form-control" id="lwEmailField" value="<%= __tData?.filterData?.email %>">
                        </div>
                    </div>
                    <div class="mb-3 row">
                        <label for="lwGroupsField" class="col-sm-2 col-form-label">{{ __tr('Group') }}</label>
                        <div class="col-sm-10">
                            <x-lw.input-field type="selectize" data-lw-plugin="lwAssignUserField" id="lwGroupsField"
                                class="lw-contact-filter-selectize" name="group_ids[]" data-selected="[<%= __tData?.filterData?.group_ids %>]" multiple>
                                <x-slot name="selectOptions">
                                    <option value="">{{ __tr('Select Group') }}</option>
                                <% _.forEach(__tData.groupData, function(item) { %>
                                        <option value="<%= item._id %>"><%= item.title %></option>
                                    <% }) %>
                                </x-slot>
                            </x-lw.input-field>
                        </div>
                    </div>
                    <div class="mb-3 row">
                        <label for="lwAssignUserField" class="col-sm-2 col-form-label">{{ __tr('Assign User') }}</label>
                        <div class="col-sm-10">
                            <x-lw.input-field type="selectize" data-lw-plugin="lwAssignUserField" id="lwCountryField"
                                class="lw-contact-filter-selectize" name="assigned_users_ids[]" data-selected="[<%= __tData?.filterData?.assigned_users_ids %>]" multiple>
                                <x-slot name="selectOptions">
                                    <option value="">{{ __tr('Select Assign User') }}</option>
                                    <option value="null">{{ __tr('Unassigned') }}</option>
                                    <% _.forEach(__tData.teamMembers, function(item) { %>
                                        <option value="<%= item._id %>"><%= item.first_name %> <%= item.last_name %></option>
                                    <% }) %>
                                </x-slot>
                            </x-lw.input-field>
                        </div>
                    </div>

                    <div class="mb-3 row">
                        <label for="lwAssignLabelsField" class="col-sm-2 col-form-label">{{ __tr('Labels/Tags') }}</label>
                        <div class="col-sm-10">
                            <x-lw.input-field type="selectize" data-lw-plugin="lwSelectize" id="lwAssignLabelsField" data-form-group-class="" class="lw-contact-filter-selectize" name="contact_labels[]" data-selected="[<%= __tData?.filterData?.contact_labels %>]" multiple >
                                <x-slot name="selectOptions">
                                <option value="">{{ __tr('Select Labels') }}</option>
                                    <% _.forEach(__tData.allLabels, function(item) { %>
                                        <option value="<%= item._id %>"><%= item.title %></option>
                                    <% }) %>
                                </x-slot>
                            </x-lw.input-field>
                        </div>
                    </div>

                    <div class="mb-3 row">
                        <label for="lwCreatedAtField" class="col-sm-2 col-form-label mt-4">{{ __tr('Created') }}</label>
                        <div class="col-sm-5">
                            <label for="lwStartDateField">{{ __tr('From') }}</label>
                            <input type="date" name="msg_start_date" class="form-control" id="lwStartDateField" value="<%= __tData?.filterData?.msg_start_date %>">
                        </div>
                        <div class="col-sm-5">
                            <label for="lwEndDateField">{{ __tr('Till') }}</label>
                            <input type="date" name="msg_end_date" class="form-control" id="lwEndDateField" value="<%= __tData?.filterData?.msg_end_date %>">
                        </div>
                    </div>
                </fieldset>

                <fieldset>
                    <legend>{{  __tr('Operational') }}</legend>                
                    <div class="mb-3 row ml-4">
                        <label for="lwFilterOptOutMarketingMessages" class="flex items-center my-3">
                            <input id="lwFilterOptOutMarketingMessages" type="checkbox" name="whatsapp_opt_out" data-size="small" class="form-checkbox" data-lw-plugin="lwSwitchery" <%= __tData?.filterData?.whatsapp_opt_out == 'on' ? 'checked' : '' %>> <span class="mr-4 text-gray-600">{{  __tr('Marketing Opted Out') }}</span>
                        </label>
                        
                        <label for="lwFilterEnableAiChatBot" class="flex items-center my-3">
                            <input id="lwFilterEnableAiChatBot" type="checkbox" name="enable_ai_bot" class="form-checkbox" data-size="small" data-lw-plugin="lwSwitchery" <%= __tData?.filterData?.enable_ai_bot == 'on' ? 'checked' : '' %>> <span class="mr-4 text-gray-600">{{  __tr('AI Bot Enabled') }}</span>
                        </label>

                        <label for="lwFilterEnableReplyChatBot" class="flex items-center my-3">
                            <input id="lwFilterEnableReplyChatBot" type="checkbox" name="enable_reply_bot" class="form-checkbox" data-size="small" data-lw-plugin="lwSwitchery" <%= __tData?.filterData?.enable_reply_bot == 'on' ? 'checked' : '' %>> <span class="mr-4 text-gray-600">{{  __tr('Reply Bot Enabled') }}</span>
                        </label>
                        
                        <div class="mb-3 row">
                            <div class="col-sm-12">
                                <hr>
                                <strong>{{ __tr('Service Window') }}</strong><br><br>
                                <div class="form-check form-check-inline">
                                    <input class="form-check-input" type="radio" name="whatsapp_service_window" <%= __tData?.filterData?.whatsapp_service_window == 'all' ? 'checked' : '' %> id="lwAllContact" value="all">
                                    <label class="form-check-label" for="lwAllContact">{{ __tr('All') }}</label>
                                </div>

                                <div class="form-check form-check-inline">
                                    <input class="form-check-input" type="radio" name="whatsapp_service_window" <%= __tData?.filterData?.whatsapp_service_window == 'active' ? 'checked' : '' %> id="lw24HourWindowActive" value="active">
                                    <label class="form-check-label" for="lw24HourWindowActive">{{ __tr('24-hour service window active') }}</label>
                                </div>

                                <div class="form-check form-check-inline">
                                    <input class="form-check-input" type="radio" name="whatsapp_service_window" <%= __tData?.filterData?.whatsapp_service_window == 'inactive' ? 'checked' : '' %> id="lw24HourWindowInactive" value="inactive">
                                    <label class="form-check-label" for="lw24HourWindowInactive">{{ __tr('24-hour service window inactive') }}</label>
                                </div>
                            </div>
                        </div>
                    </div>
                </fieldset>

                <fieldset>
                    <legend>{{  __tr('Custom') }}</legend>
                    <% if(!_.isEmpty(__tData.vendorContactCustomFields)) { %>
                        <%  _.forEach(__tData.vendorContactCustomFields, function(item) { %>
                            <div class="mb-3 row">
                                <label for="lwCustomField<%= item._id %>" class="col-sm-4 col-form-label"><%- item.input_name %></label>
                                <div class="col-sm-8">
                                    <input type="<%= item.input_type %>" name="custom_input_fields[<%- item.input_name %>]" class="form-control" id="lwCustomField<%= item._id %>" value="<%= __tData?.filterData?.custom_input_fields?.[item.input_name] %>">
                                </div>
                            </div>
                        <%  }); %>
                    <% } else { %>
                        <h3>{{ __tr('There are no custom fields available.') }}</h3>
                    <% } %>
                </fieldset>
            </div>
            <!-- form footer -->
            <div class="modal-footer">
                <!-- Submit Button -->
                <button type="submit" class="btn btn-primary">{{ __tr('Apply Filters') }}</button>
                <% if(__tData.isFilterApplied) { %>
                    <a title="{{  __tr('Clear Filter') }}" class="lw-btn btn btn-danger" @click="clearFilter">{{  __tr('Clear Filter') }}</a>
                <% } %>

                <button type="button" class="btn btn-secondary" data-dismiss="modal">{{ __tr('Close') }}</button>
            </div>
        </x-lw.form>
    </script>
</x-lw.modal>
<!-- Contact Filter Form -->