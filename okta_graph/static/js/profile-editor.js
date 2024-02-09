const schema = {
  "title": "Group and User Profile",
  "description": "Group and User Profile validation",
  "type": "object",
  "properties": {
    "group_names": {
        "type": "array"
    },
    "group_ids": {
        "type": "array"
    },
    "profile": {
        "type": "object",
        "patternProperties": {
            ".*": {"type": ["string", "integer", "boolean"]}
        }
    }
  },
  "required": ["group_names", "profile", "group_ids"]
}

const template = {
    "group_names": [],
    "group_ids": [],
    "profile": {}
}

$(document).ready(function() {
    const container = document.getElementById('profile_editor')
    const options = {
        history: true,
        name: "User Profile",
        mode: "text",
        showErrorTable: true,
        schema: schema,
        enableTransform: false
    }
    const editor = new JSONEditor(container, options, template)
    
    $(document).keydown(function(event){
        if (event.keyCode == 9) {
            event.preventDefault()
        }
    })

    $("body").on("focus focusout", "textarea.jsoneditor-text", function(_){
        try {
            editor.format()
        } catch (e) {}
    })

    $("body").on("keydown", "textarea.jsoneditor-text", function(event){
        if (event.keyCode != 9) {
            return
        }
        event.preventDefault()
        position = event.target.selectionStart
        first_part = event.target.value.slice(0, position)
        second_part = event.target.value.slice(position)

        new_val = first_part + "  " + second_part
        event.target.value = new_val
        event.target.selectionStart = position + 2
        event.target.selectionEnd = position + 2
    })


    $("body").on("keyup", "textarea.jsoneditor-text", function(event){
        key_map = {
            "BracketLeft": "}",
            "BraceLeft": "]",
            "Quote": "\"",
        }

        position = event.target.selectionStart
        end_position = event.target.selectionEnd
        inserted_val = event.target.value[position - 1]
        prev_val = event.target.value[position - 2]
        new_char = key_map[event.code]

       
        // Check it's a valid key code and that it isn't escaped or undefined
        if (!(event.code in key_map) || (prev_val === "\\")  || (inserted_val === undefined)) {
           return
        }
        
        first_part = event.target.value.slice(0, position)
        second_part = event.target.value.slice(position)

        new_val = first_part + new_char + second_part
        event.target.value = new_val
        event.target.selectionStart = position
        event.target.selectionEnd = position

        return
    })

    $("div.jsoneditor-menu").append('<span class="bi bi-clipboard-plus input_copy_button" title="Copy to clipboard"></span>')
})