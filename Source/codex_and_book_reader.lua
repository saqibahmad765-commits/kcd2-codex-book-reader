-- On-demand Codex reader. Guarded keyboard trigger; no automatic reading or native hooks.
-- UI names come from the installed KCD2 1.5.6 XML definitions.
local previous = KCD2CodexProbe
if previous and UIAction then
    pcall(UIAction.UnregisterElementListener, previous, "")
    pcall(UIAction.UnregisterEventSystemListener, previous, "")
end

KCD2CodexProbe = {
    version = "0.5.0-beta1", shown = false, generation = 0, instance = nil, contentInstance = nil,
    focus = nil, capture = nil, enabled = false,
}
local P = KCD2CodexProbe
pcall(Script.ReloadScript,"Scripts/Mods/codex_record_index.lua")
pcall(Script.ReloadScript,"Scripts/Mods/codex_english_text.lua")
local function log(message)
    System.LogAlways("[CodexProbe] " .. tostring(message))
end
local function sample(value, limit)
    return tostring(value):gsub("[%c]", " "):sub(1, limit or 160)
end
local function invalidate()
    P.generation = P.generation + 1
    P.capture = nil
    P.focusArgs = nil
    if not P.suppressStop then System.LogAlways("[CodexSpeech] STOP " .. P.generation) end
end

function P:FlushSpeechLog()
    local ok,err=pcall(System.ExecuteCommand,"log_flush")
    if not ok then log("Speech log flush failed: "..sample(err,160)) end
end
function P:KeyboardRestart()
    if KCD2BookProbe and KCD2BookProbe.shown then
        KCD2BookProbe:ReadBook();return
    end
    if not self.enabled or not self.shown or self.contentInstance==nil
        or not self.focus or not KCD2CodexRecordIndex[self.focus] then
        log("RESTART ignored: no selected supported text");return
    end
    self:ReadArticle()
end
function P:ReadArticle()
    invalidate()
    self:CaptureArticle()
    if not self.capture then return end
    if #self.capture.title + #self.capture.text > 19000 then
        log("READ refused: speech test length limit"); return
    end
    System.LogAlways("[CodexSpeech] READ " .. self.generation .. " " .. self.capture.id)
    log("READ requested; companion log confirms speech status")
    self:FlushSpeechLog()
end

function P:KeyboardToggle()
    if KCD2BookProbe and KCD2BookProbe.shown then
        KCD2BookProbe:KeyboardToggle();return
    end
    if not self.enabled or not self.shown or self.contentInstance == nil
        or not self.focus or not KCD2CodexRecordIndex[self.focus] then
        log("KEY ignored: no selected Codex article"); return
    end
    -- Codex pauses game time. Each key command is an explicit toggle; never debounce against that clock.
    self.keySerial = (self.keySerial or 0) + 1
    System.LogAlways("[CodexSpeech] KEYTOGGLE " .. self.generation .. " " .. self.keySerial .. " " .. self.focus)
    log("KEY Pause/Break requested Play/Pause")
    self:FlushSpeechLog()
end

function P:StopSpeech()
    invalidate()
    if self.shown and self.contentInstance ~= nil and self.focus
        and KCD2CodexRecordIndex[self.focus] then
        System.LogAlways("[CodexSpeech] STATE " .. self.generation .. " OPEN " .. self.focus)
    end
    log("STOP requested")
end

function P:OnShow(element, instance)
    invalidate()
    self.shown = true
    self.instance = tonumber(instance) or 0
    self.focus = nil
    log("OPEN instance=" .. tostring(self.instance) .. " generation=" .. self.generation)
end
function P:OnHide()
    invalidate()
    self.shown = false
    self.instance = nil
    self.contentInstance = nil
    self.focus = nil
    System.LogAlways("[CodexSpeech] STATE " .. self.generation .. " CLOSED")
    log("CLOSE generation=" .. self.generation)
end
function P:OnContentShow(element, instance, event, args)
    self.contentInstance = tonumber(instance)
    log("CONTENT OPEN element=" .. sample(element) .. " instance=" .. tostring(instance)
        .. " event=" .. sample(event))
end
function P:OnContentHide()
    invalidate()
    self.contentInstance = nil
    System.LogAlways("[CodexSpeech] STATE " .. self.generation .. " CLOSED")
    log("CONTENT CLOSE")
end
function P:OnFocus(element, instance, event, args)
    invalidate()
    if self.shown then self.focusArgs = args end
    -- A focus event alone is not authority to read a retained/hidden UI array.
    local id = type(args) == "table" and (args[0] or args.Ids or args.ids or args[1]) or nil
    self.focus = type(id) == "string" and id:sub(1, 160) or nil
    if self.shown and self.contentInstance ~= nil and self.focus
        and KCD2CodexRecordIndex[self.focus] then
        System.LogAlways("[CodexSpeech] STATE " .. self.generation .. " OPEN " .. self.focus)
    else
        System.LogAlways("[CodexSpeech] STATE " .. self.generation .. " CLOSED")
    end
    log("FOCUS callback element=" .. sample(element) .. " instance=" .. tostring(instance)
        .. " event=" .. sample(event) .. " argsType=" .. type(args))
    log("FOCUS generation=" .. self.generation .. " shown=" .. tostring(self.shown)
        .. " id=" .. sample(self.focus or "unresolved", 160))
end

local function plainText(text)
    -- Preserve paragraph boundaries and discard illustration markup for this diagnostic.
    return text:gsub("</paragraph>", "\n\n"):gsub("</years>", "\n")
        :gsub("<[^>]*>", ""):gsub("&nbsp;", " "):gsub("&lt;", "<")
        :gsub("&gt;", ">"):gsub("&quot;", '"'):gsub("&apos;", "'"):gsub("&amp;", "&")
end

function P:CaptureArticle()
    self.capture = nil
    if not self.enabled or not self.shown or self.contentInstance == nil then
        log("ARTICLE refused: codex and article panel must be open")
        return
    end
    local record = self.focus and KCD2CodexRecordIndex[self.focus]
    if not record then log("ARTICLE refused: selected identifier has no exact record match"); return end
    local title = KCD2CodexEnglishText[record.title]
    local body = KCD2CodexEnglishText[record.body]
    if type(title) ~= "string" or type(body) ~= "string" then
        log("ARTICLE refused: local English text missing"); return
    end
    if #body > 65536 then log("ARTICLE refused: diagnostic size limit"); return end
    local cleaned = plainText(body)
    self.capture = {generation=self.generation, id=self.focus, title=title,
        rawBody=body, text=cleaned, source="installed-English-snapshot"}
    log("ARTICLE title=" .. sample(title, 160) .. " id=" .. self.focus
        .. " source=installed-English-snapshot rawBytes=" .. #body .. " textBytes=" .. #cleaned)
    log("ARTICLE START " .. sample(cleaned, 220))
    log("ARTICLE END " .. sample(cleaned:sub(-220), 220))
end
function P:OnGameplayStarted()
    invalidate()
    self.shown = false
    self.instance = nil
    self.contentInstance = nil
    self.focus = nil
    System.LogAlways("[CodexSpeech] STATE " .. self.generation .. " CLOSED")
    log("RESET gameplay/load; capture cleared")
end

function P:SetEnabled(enabled,quiet)
    if enabled == self.enabled then return end
    if not enabled then
        pcall(UIAction.UnregisterElementListener, self, "")
        pcall(UIAction.UnregisterEventSystemListener, self, "")
        self.enabled = false
        self.suppressStop=quiet
        self:OnGameplayStarted()
        self.suppressStop=false
        log("disabled")
        return
    end
    local ok, err = pcall(function()
        UIAction.RegisterElementListener(self, "ApseCodexList", -1, "OnShow", "OnShow")
        UIAction.RegisterElementListener(self, "ApseCodexList", -1, "OnHide", "OnHide")
        UIAction.RegisterElementListener(self, "ApseCodexList", -1, "OnFocusChanged", "OnFocus")
        UIAction.RegisterElementListener(self, "ApseCraftingContent", -1, "OnShow", "OnContentShow")
        UIAction.RegisterElementListener(self, "ApseCraftingContent", -1, "OnHide", "OnContentHide")
        UIAction.RegisterEventSystemListener(self, "System", "OnGameplayStarted", "OnGameplayStarted")
    end)
    if not ok then
        pcall(UIAction.UnregisterElementListener, self, "")
        pcall(UIAction.UnregisterEventSystemListener, self, "")
        log("registration failed: " .. sample(err))
        return
    end
    self.enabled = true
    log("listeners registered (runtime callback behaviour still requires verification)")
end

local function describe(root)
    local lines, strings, visited = {}, {}, {}
    local nodes, bytes, truncated = 0, 0, false
    local function walk(value, path, depth)
        nodes = nodes + 1
        if nodes > 256 or depth > 4 then truncated = true; return end
        if type(value) == "string" then
            local room = 65536 - bytes
            if room <= 0 then truncated = true; return end
            local kept = value:sub(1, room)
            if #kept < #value then truncated = true end
            bytes = bytes + #kept
            strings[#strings + 1] = {path = path, text = kept}
            if #lines < 12 then
                lines[#lines + 1] = path .. " bytes=" .. #value .. " head=" .. sample(value, 160)
                    .. (#value > 160 and (" tail=" .. sample(value:sub(-100), 100)) or "")
            end
        elseif type(value) == "table" then
            if visited[value] then return end
            visited[value] = true
            local keys = {}
            for key in pairs(value) do
                if #keys >= 256 then truncated = true; break end
                if type(key) == "number" or type(key) == "string" then keys[#keys + 1] = key end
            end
            table.sort(keys, function(a, b)
                if type(a) == type(b) and type(a) == "number" then return a < b end
                return type(a) .. tostring(a) < type(b) .. tostring(b)
            end)
            for _, key in ipairs(keys) do
                if nodes >= 256 or bytes >= 65536 then truncated = true; break end
                walk(value[key], path .. "[" .. sample(key, 60) .. "]", depth + 1)
            end
        end
    end
    walk(root, "CodexContent", 0)
    return lines, strings, bytes, truncated
end

function P:Capture()
    self.capture = nil
    if not self.enabled or not self.shown or self.instance == nil then
        log("capture refused: no verified codex OPEN callback. Open/reopen a codex entry, then retry.")
        return
    end
    if not UIAction or type(UIAction.GetArray) ~= "function" then
        log("GetArray unavailable; no capture")
        return
    end
    -- Manual-only bounded event inspection; no text lookup or enumeration of locked entries.
    local seen, count = {}, 0
    local function inspect(value, path, depth)
        if count >= 40 or depth > 3 then return end
        if type(value) == "table" then
            if seen[value] then return end
            seen[value] = true
            for k, v in pairs(value) do
                if count >= 40 then break end
                if type(k) == "string" or type(k) == "number" then
                    inspect(v, path .. "[" .. sample(k, 60) .. "]", depth + 1)
                end
            end
        else
            count = count + 1
            log("EVENT " .. path .. " type=" .. type(value) .. " value=" .. sample(value, 200))
            if type(value) == "string" and KCD2CodexRecordIndex then
                local record = KCD2CodexRecordIndex[value]
                if record then
                    log("MATCH titleKey=" .. record.title .. " bodyKey=" .. record.body)
                end
            end
        end
    end
    inspect(self.focusArgs, "focus", 0)
    if self.contentInstance == nil then
        log("capture refused: article panel has not reported OPEN; no instance guessed")
        return
    end
    local generation = self.generation
    local ok, content = pcall(UIAction.GetArray, "ApseCraftingContent", self.contentInstance, "CodexContent")
    if not ok then log("GetArray failed: " .. sample(content)); return end
    if type(content) ~= "table" then log("GetArray returned " .. type(content) .. "; no capture"); return end
    local lines, strings, bytes, truncated = describe(content)
    if generation ~= self.generation or not self.shown then log("capture invalidated"); return end
    -- This is diagnostic structure, not yet a validated title/body or speech ordering.
    self.capture = {generation = generation, strings = strings, bytes = bytes, truncated = truncated}
    log("CAPTURE generation=" .. generation .. " strings=" .. #strings .. " bytes=" .. bytes
        .. " truncated=" .. tostring(truncated) .. " instance=" .. self.contentInstance)
    for _, line in ipairs(lines) do log(line) end
    if #strings > #lines then log("remaining string previews suppressed") end
end

function P:Command(line)
    local command = tostring(line or ""):match("^%s*(%S*)")
    if command == "off" then self:SetEnabled(false)
    elseif command == "on" then self:SetEnabled(true)
    elseif command == "status" then
        log("v" .. self.version .. " enabled=" .. tostring(self.enabled) .. " shown=" .. tostring(self.shown)
            .. " generation=" .. self.generation .. " capture=" .. tostring(self.capture ~= nil))
    else self:Capture() end
end

System.AddCCommand("cdx_probe", "KCD2CodexProbe:CaptureArticle()", "Retrieve selected codex article from local English snapshot")
System.AddCCommand("cdx_read", "KCD2CodexProbe:ReadArticle()", "Read selected codex article with speech companion")
System.AddCCommand("cdx_toggle", "KCD2CodexProbe:KeyboardToggle()", "Play/pause current Codex or book text (Pause/Break)")
System.AddCCommand("cdx_restart", "KCD2CodexProbe:KeyboardRestart()", "Restart current Codex or book text (Scroll Lock)")
System.AddCCommand("cdx_keys_off", "KCD2ReaderMCM:ReleaseKeys()", "Remove reader Pause/Break and Scroll Lock bindings")
System.AddCCommand("cdx_stop", "KCD2CodexProbe:StopSpeech()", "Stop codex speech")
System.AddCCommand("cdx_probe_status", "KCD2CodexProbe:Command('status')", "Show capture probe state")
System.AddCCommand("cdx_probe_off", "KCD2CodexProbe:SetEnabled(false)", "Disable codex probe listeners")
System.AddCCommand("cdx_probe_on", "KCD2CodexProbe:SetEnabled(true)", "Enable codex probe listeners; reopen codex afterwards")
log("v"..P.version.." loaded; feature listeners and keys await persisted reader settings")
-- Both capture modules start dormant. The settings adapter enables the chosen features.
Script.ReloadScript("Scripts/Mods/book_probe.lua")

Script.ReloadScript("Scripts/Mods/reader_mcm.lua")
