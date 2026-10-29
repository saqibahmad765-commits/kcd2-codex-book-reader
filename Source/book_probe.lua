pcall(Script.ReloadScript,"Scripts/Mods/book_item_index.lua")
pcall(Script.ReloadScript,"Scripts/Mods/book_text_snapshot.lua")
-- Manual book preview and whole-book speech; no page-turn control.
local previous = KCD2BookProbe
if previous and previous.StopSpeech then pcall(previous.StopSpeech, previous) end
if previous and previous.RestoreHooks then pcall(previous.RestoreHooks, previous) end
if previous and UIAction then
    pcall(UIAction.UnregisterElementListener, previous, "")
    pcall(UIAction.UnregisterEventSystemListener, previous, "")
end
KCD2BookProbe = {shown=false, instance=nil, generation=0, enabled=false, sample=nil}
local B = KCD2BookProbe
local function log(s) System.LogAlways("[BookProbe] " .. tostring(s)) end
local function preview(s, n) return tostring(s):gsub("[%c]", " "):sub(1,n) end




-- Convert unsigned 64-bit decimal text without ever representing the whole ID
-- as a Lua double. Division uses only values 0..159, which remain exact.
function B:NormalizeNativeId(value)
    if type(value)~="string" then return nil end
    local hex=value:match("^w(%x+)$")
    if hex then
        if #hex>16 then return nil end
        return "w"..string.rep("0",16-#hex)..hex:lower()
    end
    if not value:match("^%d+$") then return nil end
    local decimal=value:gsub("^0+","")
    if decimal=="" then decimal="0" end
    if #decimal>20 or (#decimal==20 and decimal>"18446744073709551615") then return nil end
    local reversed={}
    repeat
        local quotient,carry={},0
        for i=1,#decimal do
            local small=carry*10+tonumber(decimal:sub(i,i))
            local digit=math.floor(small/16)
            carry=small-digit*16
            if digit~=0 or #quotient>0 then quotient[#quotient+1]=tostring(digit) end
        end
        reversed[#reversed+1]=("0123456789abcdef"):sub(carry+1,carry+1)
        decimal=table.concat(quotient)
    until decimal==""
    local digits={}
    for i=#reversed,1,-1 do digits[#digits+1]=reversed[i] end
    local result=table.concat(digits)
    return "w"..string.rep("0",16-#result)..result
end

function B:BuildNativeIndex()
    self.nativeItems={}
    if not player or not player.inventory then log("ITEM NATIVE inventory unavailable");return end
    local ok,items=pcall(function() return player.inventory:GetInventoryTable() end)
    if not ok or type(items)~="table" then log("ITEM NATIVE inventory table unavailable");return end
    local scanned,mapped,failed=0,0,0
    for _,native in pairs(items) do
        scanned=scanned+1
        if scanned>16384 then log("ITEM NATIVE inventory scan capped at 16384");break end
        local serialized
        if Framework and type(Framework.WUIDToMsg)=="function" then
            local success,result=pcall(Framework.WUIDToMsg,native)
            if success and type(result)=="string" then serialized=result end
        end
        if not serialized and type(native)=="string" then serialized=native end
        if scanned<=3 then
            log("ITEM NATIVE example type="..type(native).." serialized="..preview(serialized,160))
        end
        local key=self:NormalizeNativeId(serialized)
        if key then
            if self.nativeItems[key]==nil then self.nativeItems[key]=native;mapped=mapped+1
            else self.nativeItems[key]=false end -- Never pick an ambiguous match.
        else failed=failed+1 end
    end
    log("ITEM NATIVE scanned="..math.min(scanned,16384).." mapped="..mapped.." serializationFailed="..failed)
end

function B:ResolveInventory(ids,quiet)
    local log=quiet and function() end or log
    self.focusedItem=nil
    if type(ids)~="string" or not ids:match("^w%x+$") then
        log("ITEM focus unresolved: empty, malformed or multiple instances");return
    end
    if not ItemManager or type(ItemManager.GetItem)~="function" then log("ITEM API unavailable");return end
    if not self.nativeItems then self:BuildNativeIndex() end
    local key=self:NormalizeNativeId(ids)
    local native=key and self.nativeItems and self.nativeItems[key]
    if not native then log("ITEM NATIVE no unique exact match for "..ids);return end
    log("ITEM NATIVE exact selected match="..ids.." type="..type(native))
    local ok,item=pcall(ItemManager.GetItem,native)
    if not ok or type(item)~="table" then log("ITEM lookup failed/returned "..type(item));return end
    local class=item.class
    log("ITEM FOCUS instance="..ids.." class="..preview(class,160))
    local record=type(class)=="string" and KCD2BookClassIndex[class]
    if not record then log("ITEM not an exact indexed Document match; candidate cleared");return end
    self.focusedItem={route="inventory-focus-candidate",id=ids,class=class,titleKey=record.titleKey}
    log("ITEM DOCUMENT title="..preview(record.title,200).." name="..record.name.." partKeys="..preview(record.parts,1000))
end
function B:OnInventoryShow()
    if self.shown then self:OnHide();log("INVALIDATED: inventory reopened") end
    self.inventoryEvents=0;self.focusedItem=nil;self.nativeItems=nil
end
function B:Arm()
    if self.speechSession then self:StopSpeech() end
    self.inventoryEvents=0;self.focusedItem=nil;self.nativeItems=nil
    log("Inventory lookup reset; automatically ready, use Pause/Break in a supported book")
end
function B:OnInventoryEvent(element,instance,event,args)
    if not self.enabled then return end
    -- Native book close did not always emit GeneralBook.OnHide. Inventory
    -- interaction is conservative evidence that the reading session ended.
    if self.shown then self:OnHide();log("INVALIDATED: inventory interaction resumed") end
    self.inventoryEvents=(self.inventoryEvents or 0)+1
    if event=="OnFocusChanged" then
        self:ResolveInventory(type(args)=="table" and (args[0] or args.Ids or args.ids or args[1]) or nil,self.inventoryEvents>40)
    end
    if self.inventoryEvents>40 then return end -- Cap diagnostics, not identification.
    log("INVENTORY event="..preview(event,60).." instance="..preview(instance,80))
    if type(args)=="table" then
        local count=0
        for key,value in pairs(args) do
            if count>=8 then break end
            if (type(key)=="number" or type(key)=="string") and type(value)~="table" and type(value)~="function" then
                log("INVENTORY arg["..preview(key,60).."]="..preview(value,160));count=count+1
            end
        end
    end
    -- Focus alone never requests speech; an open book and manual read are required.
end
function B:OnGameplayReset()
    self:OnHide();self.inventoryEvents=0;self.focusedItem=nil;self.nativeItems=nil
end
function B:ReportEntry()
    local entry=self.currentEntry
    if not entry then log("ENTRY CURRENT unresolved; no book assumed");return end
    log("ENTRY CURRENT route="..entry.route.." entity="..preview(entry.id,80).." titleKey="..preview(entry.titleKey,160))
    local matches=type(entry.titleKey)=="string" and KCD2BookItemIndex[entry.titleKey:gsub("^@","")]
    for i=1,math.min(matches and #matches or 0,4) do
        local record=matches[i]
        log("ENTRY MATCH title="..preview(record.title,200).." id="..record.id.." name="..record.name.." titleKey="..record.titleKey.." partKeys="..preview(record.parts,1000))
    end
end


function B:PreviewText()
    if not self.enabled or not self.shown or self.instance==nil or not self.currentEntry then
        log("TEXT refused: no open identified book");return
    end
    local snapshot=KCD2BookPreviewIndex and KCD2BookPreviewIndex[self.currentEntry.class]
    if not snapshot then log("TEXT no preview snapshot for this item class");return end
    log("TEXT BOOK title="..preview(snapshot.title,200).." parts="..#snapshot.parts
        .." scope=whole-book-ordered-parts; visible spread not yet established")
    local bytes=0
    for i=1,math.min(#snapshot.parts,16) do
        local part=snapshot.parts[i]
        local raw=part.text
        if type(raw)~="string" or bytes+#raw>65536 then log("TEXT refused: missing/oversize part");return end
        bytes=bytes+#raw
        local plain=raw:gsub("</title>","\n"):gsub("</subtitle>","\n")
            :gsub("</paragraph>","\n"):gsub("<newpage%s*/>"," [PAGE BREAK] "):gsub("<[^>]*>","")
            :gsub("&nbsp;"," "):gsub("&amp;","&"):gsub("&quot;",'"'):gsub("&apos;","'")
        log("TEXT PART "..i.." key="..part.key.." bytes="..#raw.." source="..preview(part.source,200))
        log("TEXT HEAD "..preview(plain,1200))
        log("TEXT TAIL "..preview(plain:sub(-400),400))
    end
    log("TEXT PREVIEW complete; no speech requested")
end

function B:FlushSpeechLog()
    -- The companion tails the file, not the console. Flush each complete command.
    if type(System.ExecuteCommand)~="function" then
        log("TRANSPORT flush unavailable; delivery latency unverified");return
    end
    local ok,err=pcall(System.ExecuteCommand,"log_flush")
    if not ok then log("TRANSPORT flush failed: "..preview(err,160)) end
end
function B:StopSpeech()
    self.speechGeneration=(self.speechGeneration or 0)+1
    self.speechSession=false
    System.LogAlways("[BookSpeech] STOP "..self.speechGeneration)
    self:FlushSpeechLog()
end
function B:ReadBook()
    if not self.enabled or not self.shown or self.instance==nil or not self.currentEntry then
        log("READ refused: no open identified book");return
    end
    local class=self.currentEntry.class
    local snapshot=KCD2BookPreviewIndex and KCD2BookPreviewIndex[class]
    if not snapshot or not snapshot.parts or #snapshot.parts==0 or #snapshot.parts>16 then
        log("READ refused: no supported whole-book snapshot");return
    end
    local bytes=0
    for _,part in ipairs(snapshot.parts) do
        if type(part.text)~="string" then log("READ refused: missing content");return end
        bytes=bytes+#part.text
    end
    if bytes>19000 then log("READ refused: speech test length limit");return end
    self:StopSpeech()
    self.speechSession=true
    System.LogAlways("[BookSpeech] STATE "..self.speechGeneration.." OPEN "..class)
    System.LogAlways("[BookSpeech] READ "..self.speechGeneration.." "..class)
    log("READ whole book requested; companion confirms speech status")
    self:FlushSpeechLog()
end

function B:KeyboardToggle()
    if not self.enabled or not self.shown or self.instance==nil or not self.currentEntry
        or not KCD2BookPreviewIndex[self.currentEntry.class] then
        log("PLAY/PAUSE refused: no supported open book");return
    end
    if not self.speechSession then self:ReadBook();return end
    self.keySerial=(self.keySerial or 0)+1
    System.LogAlways("[BookSpeech] TOGGLE "..self.speechGeneration.." "..self.keySerial.." "..self.currentEntry.class)
    self:FlushSpeechLog()
end

function B:Clear()
    self.generation = self.generation + 1
    self.sample = nil
end
function B:OnShow(element, instance)
    if self.speechSession then self:StopSpeech() end
    self:Clear()
    self.currentEntry=self.focusedItem;self.focusedItem=nil
    -- Open captures the focus candidate; only an explicit read command requests speech.
    self.instance = tonumber(instance)
    self.shown = self.instance ~= nil
    log("OPEN instance=" .. tostring(self.instance))
end
function B:OnHide()
    if self.speechSession then self:StopSpeech() end
    self:Clear(); self.shown=false; self.instance=nil
    self.currentEntry=nil;self.pendingEntry=nil;self.focusedItem=nil;self.nativeItems=nil
    log("CLOSE; sample cleared")
end
function B:OnPosition(element, instance, event, args)
    self:Clear()
    log("POSITION instance=" .. tostring(instance) .. " shown=" .. tostring(self.shown))
    if type(args)=="table" then
        local count=0
        for k,v in pairs(args) do
            if count>=12 then break end
            if (type(k)=="string" or type(k)=="number") and
                (type(v)=="boolean" or type(v)=="number" or type(v)=="string") then
                log("POSITION " .. preview(k,60) .. "=" .. preview(v,160)); count=count+1
            end
        end
    end
end

-- Read-only candidate inspection. No candidate is assumed to be the open book.
function B:InspectIdentity()
    if not self.enabled or not self.shown or self.instance==nil then
        log("IDENTITY refused: book must be open"); return
    end
    if not System.GetEntitiesByClass then log("IDENTITY entity enumeration unavailable"); return end
    local ok,entities=pcall(System.GetEntitiesByClass,"Book")
    if not ok or type(entities)~="table" then
        log("IDENTITY enumeration failed/returned "..type(entities)); return
    end
    local candidates,scanned={},0
    for _,entity in pairs(entities) do
        scanned=scanned+1
        if scanned>128 then log("IDENTITY enumeration capped at 128"); break end
        if type(entity)=="table" then candidates[#candidates+1]=entity end
    end
    local function active(entity)
        return player and player.id~=nil and entity.nUserId~=nil
            and tostring(entity.nUserId)==tostring(player.id)
    end
    table.sort(candidates,function(a,b)
        if active(a)~=active(b) then return active(a) end
        return tostring(a.id)<tostring(b.id)
    end)
    log("IDENTITY candidates="..#candidates.." player="..preview(player and player.id,80))
    for i=1,math.min(#candidates,16) do
        local entity=candidates[i]
        log("ENTITY id="..preview(entity.id,80).." class="..preview(entity.class,80)
            .." user="..preview(entity.nUserId,80).." playerMatched="..tostring(active(entity) or false)
            .." gfx="..preview(entity.GfxName,80).." layout="..preview(entity.ContentLayout,80))
        local content=entity.ContentText
        log("ENTITY ContentText type="..type(content))
        if type(content)=="string" then
            log("ENTITY ContentText bytes="..#content.." head="..preview(content,1600).." tail="..preview(content:sub(-400),400))
        elseif type(content)=="table" then
            local count=0
            for k,v in pairs(content) do
                count=count+1; if count>12 then log("ENTITY ContentText previews capped"); break end
                if type(k)=="number" or type(k)=="string" then
                    log("ENTITY ContentText["..preview(k,60).."] type="..type(v).." value="
                        ..((type(v)=="string" or type(v)=="number" or type(v)=="boolean") and preview(v,1200) or "<not traversed>"))
                end
            end
        end
        if entity.item then
            local nameOk,name=pcall(function() return entity.item:GetUIName() end)
            log("ENTITY item UIName="..(nameOk and preview(name,160) or "<unavailable>"))
            if nameOk and type(name)=="string" then
                local matches=KCD2BookItemIndex and KCD2BookItemIndex[name:gsub("^@","")]
                if matches then
                    for j=1,math.min(#matches,4) do
                        local record=matches[j]
                        log("ITEM MATCH id="..record.id.." name="..record.name.." titleKey="..record.titleKey.." partKeys="..preview(record.parts,1000))
                    end
                else log("ITEM no exact base-table title-key match") end
            end
        end
    end
    if #candidates>16 then log("IDENTITY further entity previews suppressed") end
end

function B:Capture()
    self.sample=nil
    if not self.enabled or not self.shown or self.instance==nil then
        log("REFUSED: open/reopen a book first; no instance guessed"); return
    end
    self:ReportEntry(); self:PreviewText()
    local generation=self.generation
    local ok,texts=pcall(UIAction.GetArray,"GeneralBook",self.instance,"Texts")
    if not ok then log("GetArray failed: " .. preview(texts,200)); return end
    if type(texts)~="table" then log("GetArray returned " .. type(texts)); return end
    local strings,seen={},{}
    local nodes,bytes,truncated=0,0,false
    local function walk(value,path,depth)
        if nodes>=256 or depth>4 then truncated=true; return end
        nodes=nodes+1
        if type(value)=="string" then
            local room=65536-bytes
            if room<=0 or #strings>=64 then truncated=true; return end
            local kept=value:sub(1,room); bytes=bytes+#kept
            if #kept<#value then truncated=true end
            strings[#strings+1]={path=path,text=kept}
        elseif type(value)=="table" then
            if seen[value] then return end
            seen[value]=true
            local keys={}
            for k in pairs(value) do
                if #keys>=256 then truncated=true; break end
                if type(k)=="number" or type(k)=="string" then keys[#keys+1]=k end
            end
            table.sort(keys,function(a,b)
                if type(a)==type(b) and type(a)=="number" then return a<b end
                return type(a)..tostring(a)<type(b)..tostring(b)
            end)
            for _,k in ipairs(keys) do
                if nodes>=256 or bytes>=65536 or #strings>=64 then truncated=true; break end
                walk(value[k],path.."["..preview(k,60).."]",depth+1)
            end
        end
    end
    walk(texts,"Texts",0)
    if generation~=self.generation or not self.shown then log("REFUSED: sample invalidated"); return end
    self.sample={strings=strings,bytes=bytes,truncated=truncated}
    log("CAPTURE generation="..generation.." instance="..self.instance.." strings="..#strings.." bytes="..bytes.." truncated="..tostring(truncated))
    for i=1,math.min(#strings,16) do
        local item=strings[i]
        log(item.path.." bytes="..#item.text.." head="..preview(item.text,1200).." tail="..preview(item.text:sub(-400),400))
    end
    if #strings>16 then log("Further previews suppressed") end
end
function B:SetEnabled(enabled)
    if self.enabled==enabled then return end
    if not enabled then
        pcall(UIAction.UnregisterElementListener,self,"")
        pcall(UIAction.UnregisterEventSystemListener,self,"")
        self.enabled=false; self:OnHide(); return
    end
    local ok,err=pcall(function()
        UIAction.RegisterElementListener(self,"GeneralBook",-1,"OnShow","OnShow")
        UIAction.RegisterElementListener(self,"GeneralBook",-1,"OnHide","OnHide")
        UIAction.RegisterElementListener(self,"GeneralBook",-1,"OnBookPosition","OnPosition")
        UIAction.RegisterElementListener(self,"ApseInventoryList",-1,"OnShow","OnInventoryShow")
        UIAction.RegisterElementListener(self,"ApseInventoryList",-1,"OnFocusChanged","OnInventoryEvent")
        UIAction.RegisterElementListener(self,"ApseInventoryList",-1,"OnGeneralEvent","OnInventoryEvent")
        UIAction.RegisterElementListener(self,"ApseInventoryList",-1,"OnDoubleClicked","OnInventoryEvent")
        UIAction.RegisterEventSystemListener(self,"System","OnGameplayStarted","OnGameplayReset")
    end)
    if not ok then
        pcall(UIAction.UnregisterElementListener,self,"")
        pcall(UIAction.UnregisterEventSystemListener,self,"")
        log("Registration failed: "..preview(err,200)); return
    end
    self.enabled=true
    log("Listeners registered; manual capture only, runtime verification required")
end
System.AddCCommand("cdx_book_probe","KCD2BookProbe:Capture()","Sample open book Texts array; no speech")
System.AddCCommand("cdx_book_off","KCD2BookProbe:SetEnabled(false)","Disable book diagnostic")
System.AddCCommand("cdx_book_on","KCD2BookProbe:SetEnabled(true)","Enable book diagnostic; reopen book")
System.AddCCommand("cdx_book_arm","KCD2BookProbe:Arm()","Rearm inventory-item diagnostics before opening inventory")
System.AddCCommand("cdx_book_read","KCD2BookProbe:ReadBook()","Read supported open book from beginning")
System.AddCCommand("cdx_book_stop","KCD2BookProbe:StopSpeech()","Stop book speech")
System.AddCCommand("cdx_book_toggle","KCD2BookProbe:KeyboardToggle()","Play/pause supported open book")
-- Remain dormant until persisted controls explicitly enable book support.
B:SetEnabled(false)
