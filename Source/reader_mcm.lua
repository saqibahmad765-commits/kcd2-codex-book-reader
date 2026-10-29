-- Optional MCM controls; the same INI works without MCM.
local MOD="codex_and_book_reader"
local A=KCD2ReaderMCM or {sequence=0,owned={}}
KCD2ReaderMCM=A
A.owned=A.owned or {}
local keys={"none","pause","scrolllock","home","end","insert","delete","pgup","pgdn","f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12"}
local labels="Unbound|Pause / Break|Scroll Lock|Home|End|Insert|Delete|Page Up|Page Down|F1|F2|F3 (camera)|F4 (camera)|F5|F6|F7|F8|F9|F10|F11|F12"
local function integer(v,lo,hi) return type(v)=="number" and v==math.floor(v) and v>=lo and v<=hi end
local function log(s) System.LogAlways("[ReaderMCM] "..tostring(s)) end
local function command(s) local ok,err=pcall(System.ExecuteCommand,s);if not ok then log("Command failed: "..tostring(err)) end end
function A:ReleaseKeys()
    for key in pairs(self.owned) do command("unbind "..key) end
    self.owned={}
end
function A:ApplyControls(state)
    local codex=state.ready and state.codex_enabled==1
    local books=state.ready and state.books_enabled==1
    if KCD2BookProbe and KCD2BookProbe.enabled~=books then KCD2BookProbe:SetEnabled(books) end
    if KCD2CodexProbe and KCD2CodexProbe.enabled~=codex then KCD2CodexProbe:SetEnabled(codex,true) end
    local desired={}
    if codex or books then
        if state.play_key>0 then desired[keys[state.play_key+1]]="cdx_toggle" end
        if state.restart_key>0 then desired[keys[state.restart_key+1]]="cdx_restart" end
    end
    -- Release only keys this adapter bound. New selections can replace an existing game bind.
    for key,bound in pairs(self.owned) do if desired[key]~=bound then command("unbind "..key) end end
    for key,bound in pairs(desired) do if self.owned[key]~=bound then command("bind "..key.." "..bound) end end
    self.owned=desired
    local signature=tostring(codex)..":"..tostring(books)..":"..state.play_key..":"..state.restart_key
    if signature~=self.signature then
        log("Controls applied codex="..tostring(codex).." books="..tostring(books).." play="..keys[state.play_key+1].." restart="..keys[state.restart_key+1])
        self.signature=signature
    end
end
function A:AcceptState(token,sequence,rate,ready,ok,codex,books,play,restart)
    sequence,rate=tonumber(sequence),tonumber(rate)
    codex,books,play,restart=tonumber(codex),tonumber(books),tonumber(play),tonumber(restart)
    if type(token)~="string" or not token:match("^[0-9a-f]+$") or #token~=16
        or not integer(sequence,0,999999999) or not integer(rate,-10,10)
        or (ready~="0" and ready~="1") or (ok~="0" and ok~="1")
        or not integer(codex,0,1) or not integer(books,0,1)
        or not integer(play,0,#keys-1) or not integer(restart,0,#keys-1)
        or (play>0 and play==restart) then log("Status rejected: invalid fields");return end
    local state={version=2,token=token,sequence=sequence,rate=rate,ready=ready=="1",ok=ok=="1",codex_enabled=codex,books_enabled=books,play_key=play,restart_key=restart}
    KCD2ReaderMCMState=state
    self:ApplyControls(state)
end
System.AddCCommand("cdx_mcm_state","KCD2ReaderMCM:AcceptState(%1,%2,%3,%4,%5,%6,%7,%8,%9)","Reader internal settings state")
function A:ReadState()
    KCD2ReaderMCMState=nil
    local ok=pcall(System.ExecuteCommand,"exec mods/codex_and_book_reader/reader-mcm-state.cfg")
    local state=KCD2ReaderMCMState
    if not ok or type(state)~="table" or state.version~=2 then return nil end
    if self.token~=state.token then self.token=state.token;self.sequence=state.sequence;self.pending={} end
    for field,entry in pairs(self.pending or {}) do
        if state.sequence>=entry.sequence then
            self.pending[field]=nil
            if not state.ok then log("Settings save failed; retaining saved value") end
        end
    end
    return state
end
function A:BuildMenu()
    if not MCM then return end
    local state=self:ReadState()
    MCM.AddMod(MOD,"Codex and Book Reader")
    if not state or not state.ready then
        MCM.AddCategory(MOD,"Speech helper is not ready","Start the reader normally with Steam, then reopen this menu.");return
    end
    local function current(field)
        local entry=self.pending and self.pending[field]
        if entry then return entry.value end
        return field=="piper_rate" and state.rate or state[field]
    end
    MCM.AddCategory(MOD,"Reading features","Disable books to use another audiobook mod. Disabled features have no capture/inventory listeners.")
    MCM.AddToggle(MOD,"codex_enabled","Read Codex entries","Enable our Codex capture and narration.",1)
    MCM.SetValue(MOD,"codex_enabled",current("codex_enabled"))
    MCM.AddToggle(MOD,"books_enabled","Read books","Enable our book narration and inventory listeners. Turn off for another audiobook mod.",1)
    MCM.SetValue(MOD,"books_enabled",current("books_enabled"))
    MCM.AddCategory(MOD,"Speech","Changes apply to new/restarted text. Pause/resume retains generated audio speed.")
    MCM.AddSlider(MOD,"piper_rate","Piper speech speed","Lower = slower; 0 = native speed. Does not affect local Ryan/SAPI.",-10,10,1,0," steps")
    MCM.SetValue(MOD,"piper_rate",current("piper_rate"))
    MCM.AddCategory(MOD,"Keyboard","Choose different keys. F3/F4 are used by your camera; Audio Book defaults include F2/F3/F4. Selecting a key can replace its game binding.")
    MCM.AddDropdown(MOD,"play_key","Play / pause key","Applies to whichever enabled reader screen is open.",labels,1)
    MCM.SetValue(MOD,"play_key",current("play_key"))
    MCM.AddDropdown(MOD,"restart_key","Restart text key","Restart the selected enabled text. Unbound disables this shortcut.",labels,2)
    MCM.SetValue(MOD,"restart_key",current("restart_key"))
end
function A:OnChanged(id,value)
    local valid=(id=="piper_rate" and integer(value,-10,10))
        or ((id=="codex_enabled" or id=="books_enabled") and integer(value,0,1))
        or ((id=="play_key" or id=="restart_key") and integer(value,0,#keys-1))
    if not valid then return end
    local state=self:ReadState()
    if not state or not state.ready then log("Settings change refused: helper not ready");return end
    self.sequence=math.max(self.sequence or 0,state.sequence)+1
    if self.sequence>999999999 then return end
    self.pending=self.pending or {};self.pending[id]={sequence=self.sequence,value=value}
    if id=="piper_rate" then System.LogAlways("[CodexReaderSettings] SET_RATE "..self.token.." "..self.sequence.." "..value)
    else System.LogAlways("[CodexReaderSettings] SET_OPTION "..self.token.." "..self.sequence.." "..id.." "..value) end
    command("log_flush")
    self.ackGeneration=(self.ackGeneration or 0)+1
    local generation=self.ackGeneration
    local function check(attempt)
        if self.ackGeneration~=generation then return end
        self:ReadState()
        if next(self.pending or {}) and attempt<20 and Script and Script.SetTimer then
            Script.SetTimer(250,function() check(attempt+1) end)
        end
    end
    if Script and Script.SetTimer then Script.SetTimer(250,function() check(1) end) end
end
function A:Synchronize(attempt)
    local state=self:ReadState()
    if state and state.ready then return end
    if attempt<25 and Script and Script.SetTimer then Script.SetTimer(1000,function() self:Synchronize(attempt+1) end) end
end
function A:OnGameplayStarted() self:Synchronize(0) end
if MCM and type(MCM.RegisterBuildSettingsListener)=="function" and type(MCM.RegisterValueChangeListener)=="function"
    and type(MCM.AddToggle)=="function" and type(MCM.AddDropdown)=="function" and type(MCM.SetValue)=="function" then
    if not A.registered then
        MCM.RegisterBuildSettingsListener(function() KCD2ReaderMCM:BuildMenu() end)
        MCM.RegisterValueChangeListener(MOD,function(id,value) KCD2ReaderMCM:OnChanged(id,value) end)
        A.registered=true
    end
    log("Optional reading toggles, speech speed and key selectors registered")
else log("MCM unavailable; INI controls remain active") end
if UIAction then
    pcall(UIAction.UnregisterEventSystemListener,A,"")
    pcall(UIAction.RegisterEventSystemListener,A,"System","OnGameplayStarted","OnGameplayStarted")
end
A:Synchronize(0)
