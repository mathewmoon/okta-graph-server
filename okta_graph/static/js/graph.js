var selectedArea;
var report_json;

function insert_graph(data) {
    $("div.node_info").remove()

    if ($("#download_report").is(":visible")) {
        $("#download_report").hide()
    }

    $("#cmap area").remove()
    $("#cmap").append(atob(data.map))
    
    var image = new Image()
    image.src = `data:image/png;base64,${data.image}`

    if ($("#graph_image").length != 0) {
        $("#graph_image").remove()
    }

    image.id = "graph_image"
    image.useMap = "#cmap"

    $("#graph_div").append(image)

    report_json = JSON.stringify(data.report_json, null, 2)
    $("#report_div").html(`<p><pre>${report_json}</pre></p>`)
    $("#download_report").show()
}

function load_graph(req_data) {
    res = $.ajax({
        url: "http://localhost:8000/graph",
        type: "POST",
        contentType: "application/json",
        dataType: "json",
        data: JSON.stringify(req_data),
        success: insert_graph
    })
}

function make_controls(draggable=true, pinnable=true) {
    $control_span = $(`<span class="controls"></span>`)
    $pin_span = $(`<span class="bi bi-pin-angle pin_button" title="Click to pin"></span>`)
    $drag_span = $(`<span class="bi bi-grip-horizontal move_button" title="Click and hold to drag"></span>`)
    $close_span = $(`<span class="bi bi-x-lg close_button" title="Close"></span>`)
    if (pinnable) {
        $control_span.append($pin_span)
    }

    $control_span.append($close_span)

    if (draggable) {
        $control_span.append($drag_span)
    }

    $control_span.tooltip({
        close: function(){
            $(".ui-helper-hidden-accessible").remove()
        }
    })
    return $control_span
}

function close_unpinned(remove, exceptions) {
    $("div.node_info").each(function(i, elem){
        for_node = $(elem).data("for_node")
        if (!($(elem).hasClass("pinned") || $.inArray(for_node, exceptions) >= 0)) {
            $(elem).remove()
        }
    })
    selectedArea = null
}

function make_info_table(node, event) {
    if ($(`#node_info_${node.id}`).length != 0) {
        console.log("Already exists")
        $(`#node_info_${node.id}`).show()
        return $(`#node_info_${node.id}`)
    }
    $div = $(`<div></div>`)
    $div.data("for_node", node.id)
    $div.append(make_controls(draggable=true, pinnable=true))
    $table = $(`<table"></table>`)
    $div.addClass("node_info")
    $table.addClass("node_info")
    
    lines = node.title.split("\n")
    console.log(lines)
    node_name = null
    data = {}
    
    start_aws = lines.indexOf("AWS Account/Role Assignments:")
    if (start_aws > -1) {
        common_lines = lines.slice(0, start_aws)
        aws_lines = lines.slice(start_aws + 1)
        aws_header = $(`<h4>AWS Account/Role Assignments</h4>`)
    } else {
        common_lines = lines
        aws_lines = null
    }
    
    console.log(aws_lines)
    $.each(common_lines, function(){
        if (this.length !== 0) {
            fields = this.split(":")
            k = fields.shift().replace("Rule ", "")
            v = fields.join(":")
            if (k == "Name") {
                node_name = v
            }
            data[k] = v
        }
    })
    
    $div.append($(`<h4>${node_name}</h4>`))

    $.each(data, function(k, v){
        $row = $("<tr></tr>")
        $key =$(`<td></td>`)
        $key.append(` ${k}:`)
        $key.addClass("node_info_key")
        $row.append($key)
        $val = $(`<td title="Click to copy to clipboard">${v}</td>`)
        $val.addClass("node_info_value")
        $val.tooltip({
            hide: {duration: 0},
            show: {effect: "fadeIn", duration: 300}
        })
        $row.append($val)
        $table.append($row)                
    })

    $div.append($table)


    if (aws_lines !== null) {
        data = {}
        $.each(aws_lines, function(){
            if (this.length !== 0) {
                fields = this.split(":")
                k = fields.shift()
                v = fields.join(":")
                data[k] = v
            }
        })
        $div.append(aws_header)
        $aws_table = $(`<table"></table>`)
        $aws_table.addClass("node_info")
        $.each(data, function(k, v){
            account_name = k
            $row = $("<tr></tr>")
            $key =$(`<td title=></td>`)
            $key.append(` ${k}:`)
            $key.addClass("node_info_key")
            $row.append($key)
            $val = $(`<td>${v}</td>`)
            $val.addClass("node_info_value")
            $row.append($val)
            $aws_table.append($row)                
        })
        $div.append($aws_table)
    }

    // Where the mouse was on the click event
    x = Math.abs(event.clientX)
    y = Math.abs(event.clientY)
    
    x_px = `${x}px`
    y_px = `${y}px`
    $div.css({"top": y_px, "left": x_px})
    info_width = $div.width()
    
    $("#main").append($div)
    $div.draggable({handle: "span.move_button"})
    height = Math.ceil($div.height())
    width = Math.ceil($div.width())
    $div.resizable({
        minHeight: height,
        minWidth: width
    })
    $(".node_info td").addClass("node_info")

    return $div
}


function toggle_report(op) {
    if (op == "hide" && $("#report_div_wrapper").is(":visible")) {
        $("#report_div_wrapper").hide()
    }

    if (op == "show" && !$("#report_div_wrapper").is(":visible")) {
        $("#report_div_wrapper").css("display", "flex")
        $("#report_div_wrapper").show()
    }
}

function copy_to_clipboard(data, source) {
    $temp = $(`<textarea id="copy_temp_input">`)
    $temp.addClass("temp_input")
    $temp.val(data)
    $("body").append($temp)
    $temp.select()
    document.execCommand("copy")
    $temp.remove()

    source.tooltip({content: "Copied!"})

    setTimeout(function(){
        source.tooltip({content: "Click to copy to clipboard"})
    }, 1000)
}

$("document").ready(function(){

    $("span.bi").tooltip()

    $("body").on("click", "area", function(event) {
        if (this.id === selectedArea) {
            return
        }
        selectedArea = this.id
        $div = make_info_table(this, event)
        close_unpinned(true, [this.id])
    })

    $("body").on("click", "td.node_info_value", function(event){
        id = "node_value_input_copy"
        txt = $(event.target).html()
        $temp = $(`<input id="node_value_input_copy">`)
        $temp.addClass("temp_input")
        $temp.val(txt)
        $("body").append($temp)
        $(`#${id}`).select()
        document.execCommand("copy")
        $(`#${id}`).remove()

        $(event.target).tooltip({content: "Copied!"})

        setTimeout(function(){
            $(event.target).tooltip({content: "Click to copy to clipboard"})
        }, 1000)
    })

    $("body").on("click", "span.close_button", function(event){
        console.log("close button")
        parent = $(event.target).parent().parent()
        $(parent).remove()
        parent.hide()
        selectedArea = null
    })
    
    $("body").on("click", "#graph_image, .nav", function(_){
        toggle_report("hide")
        close_unpinned()
    })

    $("body").on("click", "#generate_graph", function(_){
        close_unpinned()
        if ($("#report_div_wrapper").is(":visible")) {
            $("#report_div_wrapper").hide()
            $("#report_div_wrapper").hide()
        }
        data = {}
        source_data = JSON.parse($("textarea.jsoneditor-text").val())
        data.group_name_input = source_data.group_names
        data.groupid_input = source_data.group_ids
        data.profile_input = source_data.profile
        
        return load_graph(data)
    })


    $("body").on("click", "span.pin_button", function(event){
        parent = $(event.target).parent().parent()
        if (parent.hasClass("pinned")) {
            parent.removeClass("pinned")
            $(event.target).removeClass("bi-pin-fill")
            $(event.target).addClass("bi-pin-angle")
            $(event.target).prop("title", "Click to pin")
            $(event.target).tooltip({content: "Click to pin"})
        } else {
            parent.addClass("pinned")
            $(event.target).removeClass("bi-pin-angle")
            $(event.target).addClass("bi-pin-fill")
            $(event.target).prop("title", "Click to unpin")
            $(event.target).tooltip({content: "Click to unpin"})
        }
    })

    $("body").on("click", "div.node_info *", function(event){
        $("div.node_info").css("z-index", 0)
        $(event.target).parents(`div[class^="node_info"]`).css("z-index", 1000)
    })

    $("body").on("click", "span.report_close_button", function(_){
        toggle_report("hide")
    })

    $("body").on("click", "span.report_copy_button", function(event){
        txt = $("#report_div pre").text()
        txt.setData
        console.log(txt)
        copy_to_clipboard(txt, $(event.target))
    })

    $("body").on("click", "span.report_download_button", function(event){
        console.log("Downloading")
        txt = $("#report_div pre").text()
        date = new Date()
        ts = String(date.getTime())

        file = new File([txt], `okta-report-${ts}.json`)
        url = URL.createObjectURL(file)

        link = $("<a/>", {
            download: file.name,
            href: url
        })
        $("#main").append(link)
        link[0].click()
        link.remove()
        window.URL.revokeObjectURL(url)

    })


    $("body").on("click", "#download_report", function(){
        console.log("SHOW REPORT")
        $("#report_div_wrapper").show({
            complete: function(){
                toggle_report("show")
            }
        })
    })

    $("body").on("click", "span.input_copy_button", function(event){
        src = $(event.source)
        txt = $("textarea.jsoneditor-text").val()
        copy_to_clipboard(txt, src)
    })

    input_help_content = `
        <p><b>Input profile and group info to run a query:</b>
        <ul>
            <li><b>roup_names:</b> Human readable names that will be translated into ID's during the query</li>
            <li><b>group_ids:</b> Group ID's as they are stored in Okta</li>
            <li><b>profile:</b> Key/Value pairs of user attributes such as \"phiaccess\" or \"countryCode\"</li>
        </ul>
        Groups input as names or ID's will are treated as if they were manual group assignments to a user.

        The results of the query will contain a graph of all groups that a user would inherit, recursively, based on the manual assignments plus
        profile attributes
        </p>

    `
    $("span.input_help").tooltip({
        content: input_help_content
    })
})

test = ['Name: AWS_Role_HingeSandboxAdmin', 'Type: Okta Group', 'Description: Admin access in Sandbox accounts', 'Group Id: 00gatdh1utKutMVQ2697', 'Group Name: AWS_Role_HingeSandboxAdmin', 'Is Recursion: False', 'AWS Account/Role Assignments:', '  infra-sre-sandbox-1 (574956111507):', '       * HingeAdmin', '  infra-sre-sandbox-2 (238535515044):', '       * HingeAdmin', '']